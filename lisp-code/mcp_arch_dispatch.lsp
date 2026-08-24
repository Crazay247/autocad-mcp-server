;;; mcp_arch_dispatch.lsp — File-based IPC dispatcher for autocad-arch-mcp v1.0 (AutoCAD 2021 + YQArch NBC)
;;;
;;; Port of autocad-mcp/lisp-code/mcp_dispatch.lsp v3.1 (1378 lines) with hardening:
;;;   C1 ACP-aware: GetACP 936->gbk else cp1252, LISP escapes \uXXXX for non-ASCII (Devanagari e.g. शयन कक्ष)
;;;   M5 key-substring: Python side uses flat-prefixed keys; LISP searches "\"key\"" quoted to avoid x vs cx collision
;;;   SECURELOAD via TRUSTEDPATHS not 0 (adds %LOCALAPPDATA%\autocad-arch-mcp\ipc to TRUSTEDPATHS, restores SECURELOAD=1)
;;;   mcp-sanitise-input on every (command ...) string arg
;;;   mcp-report-error namespaced (not report-error)
;;;   undo marker _.UNDO _BEgin/_End around YQ multi-step chains
;;;   init_yqarch_layers after purge (reloads yqstart.lsp / yqarch.vlx)
;;;   whitelist yq_wall/ad/aw/ho/wd/tw/cw/vw/xf/bg/ltj + create-quick-dim etc. -> ww/ad/aw...
;;;
;;; Protocol:
;;;   1. Python writes command JSON to %LOCALAPPDATA%/autocad-arch-mcp/ipc/<pid>/autocad_arch_cmd_{id}.json (ACP-aware encoding)
;;;   2. Python triggers (c:mcp-arch-dispatch) via PostMessageW (2x ESC + string) — alias (c:mcp-dispatch) kept for compat
;;;   3. This function reads cmd, dispatches via whitelist, writes result JSON (atomic .tmp->rename, \uXXXX escapes)
;;;   4. Python polls for autocad_arch_result_{id}.json (utf-8, HMAC-checked)
;;;
;;; SECURITY: No raw eval — dispatcher uses a command whitelist/map. mcp-sanitise-input guards injection.
;;; IPC dir: *mcp-arch-ipc-dir* per-pid under %LOCALAPPDATA%\autocad-arch-mcp\ipc\<pid> (LISP cannot get pid, so
;;;          Python sets env AUTOCAD_ARCH_IPC_DIR with pid suffix; LISP falls back to LOCALAPPDATA/ipc/ if env not set)
;;; Compatible with AutoCAD 2021+ YQArch.
;; Load dependencies
(if (not mcp-report-error)
  (defun mcp-report-error (msg) (princ (strcat "\nERROR: " msg)))
)

;; IPC directory
;; IPC directory — per-pid under %LOCALAPPDATA%\autocad-arch-mcp\ipc\<pid>
;; LISP cannot call getpid; Python side sets AUTOCAD_ARCH_IPC_DIR with pid suffix.
;; Fallback uses LOCALAPPDATA env; final fallback is hardcoded Predator path for dev.
(setq *mcp-arch-ipc-dir*
  (let ((env-dir (getenv "AUTOCAD_ARCH_IPC_DIR")))
    (if (and env-dir (> (strlen env-dir) 0))
      (if (= (substr env-dir (strlen env-dir) 1) "/")
        env-dir
        (strcat env-dir "/")
      )
      (let ((local (getenv "LOCALAPPDATA")))
        (if (and local (> (strlen local) 0))
          (strcat local "/autocad-arch-mcp/ipc/")
          "C:/Users/Predator/AppData/Local/autocad-arch-mcp/ipc/"
        )
      )
    )
  )
)
;; Compat alias for legacy code that refs *mcp-arch-ipc-dir*
(setq *mcp-ipc-dir* *mcp-arch-ipc-dir*)

;; -----------------------------------------------------------------------
;; JSON-like output helpers (minimal, no external library)
;; -----------------------------------------------------------------------

(defun mcp-write-result (filepath request-id ok-flag payload error-msg / fp)
  "Write a result JSON file. Atomic: write to .tmp then rename."
  (setq tmp-path (strcat filepath ".tmp"))
  (setq fp (open tmp-path "w"))
  (if fp
    (progn
      (write-line "{" fp)
      (write-line (strcat "  \"request_id\": \"" request-id "\",") fp)
      (if ok-flag
        (progn
          (write-line "  \"ok\": true," fp)
          (write-line (strcat "  \"payload\": " payload) fp)
        )
        (progn
          (write-line "  \"ok\": false," fp)
          (write-line (strcat "  \"error\": \"" (mcp-escape-string error-msg) "\"") fp)
        )
      )
      (write-line "}" fp)
      (close fp)
      ;; Rename .tmp to final path (atomic on NTFS)
      (vl-file-rename tmp-path filepath)
    )
    (princ (strcat "\nMCP: Cannot open result file: " tmp-path))
  )
)

(defun mcp-escape-string (s / result i ch code hex)
  "Escape string for JSON. ACP-aware: 936->gbk else cp1252 on Python side; LISP escapes control chars (<32) and non-ASCII (>127) as \\uXXXX for Devanagari e.g. \\u0936\\u092f\\u0928 (शयन कक्ष)."
  (if (null s) (setq s ""))
  (setq result "" i 1)
  (while (<= i (strlen s))
    (setq ch (substr s i 1))
    (setq code (ascii ch))
    (cond
      ((= ch "\"") (setq result (strcat result "\\\"")))
      ((= ch "\\") (setq result (strcat result "\\\\")))
      ((< code 32)
        (setq hex (mcp-int-to-hex4 code))
        (setq result (strcat result "\\u" hex))
      )
      ((> code 127)
        (setq hex (mcp-int-to-hex4 code))
        (setq result (strcat result "\\u" hex))
      )
      (t (setq result (strcat result ch)))
    )
    (setq i (1+ i))
  )
  result
)

(defun mcp-int-to-hex4 (n / hex digits rem i)
  "Convert integer 0-65535 to 4-digit hex string (zero-padded)."
  (setq digits "0123456789ABCDEF")
  (setq hex "")
  (setq i 0)
  (while (< i 4)
    (setq rem (rem n 16))
    (setq hex (strcat (substr digits (+ rem 1) 1) hex))
    (setq n (/ n 16))
    (setq i (1+ i))
  )
  hex
)

(defun mcp-sanitise-input (s / bad)
  "Reject injection chars before any (command ...) — guards \" ; ( ) ' and control chars. Returns sanitised string or nil if rejected."
  (if (null s) nil
    (if (= (type s) 'STR)
      (progn
        (cond
          ((vl-string-search "\"" s) (mcp-report-error (strcat "sanitise rejected quote: " s)) nil)
          ((vl-string-search ";" s) (mcp-report-error (strcat "sanitise rejected ;: " s)) nil)
          ((vl-string-search "(" s) (mcp-report-error (strcat "sanitise rejected (: " s)) nil)
          ((vl-string-search ")" s) (mcp-report-error (strcat "sanitise rejected ): " s)) nil)
          ((vl-string-search "'" s) (mcp-report-error (strcat "sanitise rejected apos: " s)) nil)
          ((vl-string-search (chr 10) s) (mcp-report-error "sanitise rejected newline") nil)
          ((vl-string-search (chr 13) s) (mcp-report-error "sanitise rejected cr") nil)
          ((vl-string-search "\\" s) (mcp-report-error (strcat "sanitise rejected backslash: " s)) nil)
          (t s)
        )
      )
      s
    )
  )
)

(defun mcp-read-file-lines (filepath / fp line lines)
  "Read all lines from a file into a single string."
  (setq fp (open filepath "r"))
  (if (not fp) (progn (princ (strcat "\nMCP: Cannot read: " filepath)) nil)
    (progn
      (setq lines "")
      (while (setq line (read-line fp))
        (setq lines (strcat lines line))
      )
      (close fp)
      lines
    )
  )
)

;; -----------------------------------------------------------------------
;; Simple JSON parser (extracts string values by key)
;; -----------------------------------------------------------------------

;; M5 fix: keys are flat-prefixed (Python side) to avoid x vs cx substring collision; search is quoted "\"key\""
(defun mcp-json-get-string (json key / search-str pos end-pos value)
  "Extract a string value for a given key from JSON text."
  (setq search-str (strcat "\"" key "\""))
  (setq pos (vl-string-search search-str json))
  (if (null pos) nil
    (progn
      ;; Find the colon after key
      (setq pos (vl-string-search ":" json pos))
      (if (null pos) nil
        (progn
          ;; Find opening quote of value
          (setq pos (vl-string-search "\"" json (1+ pos)))
          (if (null pos) nil
            (progn
              (setq pos (+ pos 2))  ; 0-based search result + 2 = 1-based position after quote
              ;; Find closing quote (skip escaped quotes)
              (setq end-pos pos)
              (while (and (<= end-pos (strlen json))
                          (or (= end-pos pos)
                              (/= (substr json end-pos 1) "\"")))
                ;; Handle escaped characters
                (if (= (substr json end-pos 1) "\\")
                  (setq end-pos (+ end-pos 2))
                  (setq end-pos (1+ end-pos))
                )
              )
              (substr json pos (- end-pos pos))
            )
          )
        )
      )
    )
  )
)

(defun mcp-json-get-number (json key / search-str pos num-start num-end ch)
  "Extract a number value for a given key from JSON text."
  (setq search-str (strcat "\"" key "\""))
  (setq pos (vl-string-search search-str json))
  (if (null pos) nil
    (progn
      (setq pos (vl-string-search ":" json pos))
      (if (null pos) nil
        (progn
          (setq pos (+ pos 2))  ; 0-based search result + 2 = 1-based position after colon
          ;; Skip whitespace
          (while (and (<= pos (strlen json))
                      (member (substr json pos 1) '(" " "\t" "\n")))
            (setq pos (1+ pos))
          )
          ;; Read number
          (setq num-start pos num-end pos)
          (while (and (<= num-end (strlen json))
                      (or (member (substr json num-end 1) '("0" "1" "2" "3" "4" "5" "6" "7" "8" "9" "." "-" "+"))
                      ))
            (setq num-end (1+ num-end))
          )
          (atof (substr json num-start (- num-end num-start)))
        )
      )
    )
  )
)

;; -----------------------------------------------------------------------
;; String splitting utility (used by semicolon-delimited encodings)
;; -----------------------------------------------------------------------

(defun mcp-split-string (str delim / pos result token)
  "Split a string by single-char delimiter. Returns a list of strings."
  (setq result '())
  (while (setq pos (vl-string-search delim str))
    (setq token (substr str 1 pos))
    (setq result (append result (list token)))
    (setq str (substr str (+ pos 2)))
  )
  (setq result (append result (list str)))
  result
)

;; -----------------------------------------------------------------------
;; Command dispatcher — WHITELIST ONLY, no eval
;; -----------------------------------------------------------------------

(defun mcp-dispatch-command (cmd-name params-json / result)
  "Dispatch a command by name. Returns (ok . payload-or-error)."
  (cond
    ;; --- Ping ---
    ((= cmd-name "ping")
     (cons T "\"pong\""))

    ;; --- Freehand LISP execution ---
    ((= cmd-name "execute-lisp")
     (mcp-cmd-execute-lisp params-json))

    ;; --- Undo / Redo ---
    ((= cmd-name "undo")
     (command "_.UNDO" "1") (cons T "\"undone\""))

    ((= cmd-name "redo")
     (command "_.REDO") (cons T "\"redone\""))

    ;; --- Drawing info ---
    ((= cmd-name "drawing-info")
     (mcp-cmd-drawing-info))

    ;; --- Layer operations ---
    ((= cmd-name "layer-list")
     (mcp-cmd-layer-list))

    ((= cmd-name "layer-create")
     (mcp-cmd-layer-create params-json))

    ((= cmd-name "layer-set-current")
     (mcp-cmd-layer-set-current params-json))

    ((= cmd-name "layer-set-properties")
     (mcp-cmd-layer-set-properties params-json))

    ((= cmd-name "layer-freeze")
     (mcp-cmd-layer-freeze params-json))

    ((= cmd-name "layer-thaw")
     (mcp-cmd-layer-thaw params-json))

    ((= cmd-name "layer-lock")
     (mcp-cmd-layer-lock params-json))

    ((= cmd-name "layer-unlock")
     (mcp-cmd-layer-unlock params-json))

    ;; --- Entity creation ---
    ((= cmd-name "create-line")
     (mcp-cmd-create-line params-json))

    ((= cmd-name "create-circle")
     (mcp-cmd-create-circle params-json))

    ((= cmd-name "create-polyline")
     (mcp-cmd-create-polyline params-json))

    ((= cmd-name "create-rectangle")
     (mcp-cmd-create-rectangle params-json))

    ((= cmd-name "create-text")
     (mcp-cmd-create-text params-json))

    ((= cmd-name "create-arc")
     (mcp-cmd-create-arc params-json))

    ((= cmd-name "create-ellipse")
     (mcp-cmd-create-ellipse params-json))

    ((= cmd-name "create-mtext")
     (mcp-cmd-create-mtext params-json))

    ((= cmd-name "create-hatch")
     (mcp-cmd-create-hatch params-json))

    ;; --- Entity queries ---
    ((= cmd-name "entity-count")
     (mcp-cmd-entity-count params-json))

    ((= cmd-name "entity-list")
     (mcp-cmd-entity-list params-json))

    ((= cmd-name "entity-get")
     (mcp-cmd-entity-get params-json))

    ((= cmd-name "entity-erase")
     (mcp-cmd-entity-erase params-json))

    ;; --- Entity modification ---
    ((= cmd-name "entity-move")
     (mcp-cmd-entity-move params-json))

    ((= cmd-name "entity-copy")
     (mcp-cmd-entity-copy params-json))

    ((= cmd-name "entity-rotate")
     (mcp-cmd-entity-rotate params-json))

    ((= cmd-name "entity-scale")
     (mcp-cmd-entity-scale params-json))

    ((= cmd-name "entity-mirror")
     (mcp-cmd-entity-mirror params-json))

    ((= cmd-name "entity-offset")
     (mcp-cmd-entity-offset params-json))

    ((= cmd-name "entity-array")
     (mcp-cmd-entity-array params-json))

    ((= cmd-name "entity-fillet")
     (mcp-cmd-entity-fillet params-json))

    ((= cmd-name "entity-chamfer")
     (mcp-cmd-entity-chamfer params-json))

    ;; --- View ---
    ((= cmd-name "zoom-extents")
     (command "_.ZOOM" "_E")
     (cons T "\"zoomed to extents\""))

    ((= cmd-name "zoom-window")
     (progn
       (setq x1 (mcp-json-get-number params-json "x1"))
       (setq y1 (mcp-json-get-number params-json "y1"))
       (setq x2 (mcp-json-get-number params-json "x2"))
       (setq y2 (mcp-json-get-number params-json "y2"))
       (command "_.ZOOM" "_W" (list x1 y1 0) (list x2 y2 0))
       (cons T "\"zoomed to window\"")))

    ;; --- Drawing file ops ---
    ((= cmd-name "drawing-save")
     (progn
       (setq path (mcp-json-get-string params-json "path"))
       (if (and path (> (strlen path) 0))
         (progn
           (setvar "FILEDIA" 0)
           (command "_.SAVEAS" "" path)
           (setvar "FILEDIA" 1)
           (cons T (strcat "\"saved to: " (mcp-escape-string path) "\"")))
         (progn (command "_.QSAVE") (cons T "\"saved\"")))))

    ((= cmd-name "drawing-save-as-dxf")
     (progn
       (setq path (mcp-json-get-string params-json "path"))
       (if path
         (progn (command "_.SAVEAS" "DXF" path) (cons T (strcat "\"" path "\"")))
         (cons nil "Save path required"))))

    ((= cmd-name "drawing-purge")
     (command "_.-PURGE" "_ALL" "*" "_N")
     (cons T "\"purged\""))

    ((= cmd-name "drawing-open")
     (progn
       (setq path (mcp-json-get-string params-json "path"))
       (if path
         (progn
           (setvar "FILEDIA" 0)
           (command "_.OPEN" path)
           (setvar "FILEDIA" 1)
           (cons T (strcat "\"opened: " (mcp-escape-string path) "\"")))
         (cons nil "Path required"))))

    ;; --- P&ID ---
    ((= cmd-name "pid-setup-layers")
     (if c:setup-pid-layers
       (progn (c:setup-pid-layers) (cons T "\"P&ID layers created\""))
       (cons nil "pid_tools.lsp not loaded")))

    ((= cmd-name "pid-insert-symbol")
     (mcp-cmd-pid-insert-symbol params-json))

    ((= cmd-name "pid-draw-process-line")
     (mcp-cmd-pid-draw-process-line params-json))

    ((= cmd-name "pid-connect-equipment")
     (mcp-cmd-pid-connect-equipment params-json))

    ((= cmd-name "pid-add-flow-arrow")
     (mcp-cmd-pid-add-flow-arrow params-json))

    ((= cmd-name "pid-add-equipment-tag")
     (mcp-cmd-pid-add-equipment-tag params-json))

    ((= cmd-name "pid-add-line-number")
     (mcp-cmd-pid-add-line-number params-json))

    ((= cmd-name "pid-insert-valve")
     (mcp-cmd-pid-insert-valve params-json))

    ((= cmd-name "pid-insert-instrument")
     (mcp-cmd-pid-insert-instrument params-json))

    ((= cmd-name "pid-insert-pump")
     (mcp-cmd-pid-insert-pump params-json))

    ((= cmd-name "pid-insert-tank")
     (mcp-cmd-pid-insert-tank params-json))

    ;; --- Block operations ---
    ((= cmd-name "block-list")
     (mcp-cmd-block-list))

    ((= cmd-name "block-insert")
     (mcp-cmd-block-insert params-json))

    ((= cmd-name "block-insert-with-attributes")
     (mcp-cmd-block-insert-with-attribs params-json))

    ((= cmd-name "block-get-attributes")
     (mcp-cmd-block-get-attributes params-json))

    ((= cmd-name "block-update-attribute")
     (mcp-cmd-block-update-attribute params-json))

    ((= cmd-name "block-define")
     (cons nil "block-define not available via IPC (use ezdxf backend)"))

    ;; --- Annotation ---
    ((= cmd-name "create-dimension-linear")
     (mcp-cmd-create-dimension-linear params-json))

    ((= cmd-name "create-dimension-aligned")
     (mcp-cmd-create-dimension-aligned params-json))

    ((= cmd-name "create-dimension-angular")
     (mcp-cmd-create-dimension-angular params-json))

    ((= cmd-name "create-dimension-radius")
     (mcp-cmd-create-dimension-radius params-json))

    ((= cmd-name "create-leader")
     (mcp-cmd-create-leader params-json))

    ;; --- Drawing management ---
    ((= cmd-name "drawing-create")
     (mcp-cmd-drawing-create params-json))

    ((= cmd-name "drawing-get-variables")
     (mcp-cmd-drawing-get-variables params-json))

    ((= cmd-name "drawing-plot-pdf")
     (mcp-cmd-drawing-plot-pdf params-json))

    ;; --- P&ID list symbols ---
    ((= cmd-name "pid-list-symbols")
     (mcp-cmd-pid-list-symbols params-json))

    ;; --- YQArch NBC whitelist (ww/ad/aw/ho/wd/tw/cw/vw/xf/bg/ltj etc.) ---
    ;; wall
    ((= cmd-name "yq_wall") (mcp-cmd-yq-wall params-json))
    ((= cmd-name "ww") (mcp-cmd-yq-wall params-json))
    ((= cmd-name "yq_wall_hatch") (mcp-cmd-yq-wall params-json))
    ;; door
    ((= cmd-name "yq_hole_door") (mcp-cmd-yq-hole-door params-json))
    ((= cmd-name "yq_hole") (mcp-cmd-yq-hole params-json))
    ((= cmd-name "yq_door") (mcp-cmd-yq-hole-door params-json))
    ((= cmd-name "ad") (mcp-cmd-yq-hole-door params-json))
    ((= cmd-name "ho") (mcp-cmd-yq-hole params-json))
    ;; window
    ((= cmd-name "yq_hole_win") (mcp-cmd-yq-hole-window params-json))
    ((= cmd-name "yq_hole_window") (mcp-cmd-yq-hole-window params-json))
    ((= cmd-name "yq_win") (mcp-cmd-yq-hole-window params-json))
    ((= cmd-name "wd") (mcp-cmd-yq-hole-window params-json))
    ((= cmd-name "aw") (mcp-cmd-yq-hole-window params-json))
    ;; trim/fix wall
    ((= cmd-name "yq_trim_wall") (mcp-cmd-yq-trim-wall params-json))
    ((= cmd-name "tw") (mcp-cmd-yq-trim-wall params-json))
    ((= cmd-name "yq_trim_fix_wall") (mcp-cmd-yq-trim-wall params-json))
    ;; width / move / repair windoor
    ((= cmd-name "yq_width_windoor") (mcp-cmd-yq-width-windoor params-json))
    ((= cmd-name "cw") (mcp-cmd-yq-width-windoor params-json))
    ((= cmd-name "yq_move_windoor") (mcp-cmd-yq-move-windoor params-json))
    ((= cmd-name "vw") (mcp-cmd-yq-move-windoor params-json))
    ((= cmd-name "yq_repair") (mcp-cmd-yq-repair params-json))
    ((= cmd-name "xf") (mcp-cmd-yq-repair params-json))
    ;; bg section levels
    ((= cmd-name "yq_bg") (mcp-cmd-yq-bg params-json))
    ((= cmd-name "yq_bg_section_levels") (mcp-cmd-yq-bg params-json))
    ((= cmd-name "bg") (mcp-cmd-yq-bg params-json))
    ;; stair
    ((= cmd-name "yq_stair") (mcp-cmd-yq-stair params-json))
    ((= cmd-name "yq_staircase_plan") (mcp-cmd-yq-stair params-json))
    ((= cmd-name "ltj") (mcp-cmd-yq-stair params-json))
    ;; dimension quick
    ((= cmd-name "create-quick-dim") (mcp-cmd-create-quick-dim params-json))
    ((= cmd-name "quick_dim_wall") (mcp-cmd-create-quick-dim params-json))
    ((= cmd-name "quick_dim") (mcp-cmd-create-quick-dim params-json))
    ((= cmd-name "DDZ") (mcp-cmd-create-quick-dim params-json))
    ;; dotnet invoke (TRUSTEDPATHS-gated)
    ((= cmd-name "dotnet_invoke") (mcp-cmd-execute-lisp params-json))

    ;; --- Unknown ---
    (t (cons nil (strcat "Unknown command: " cmd-name)))
  )
)

;; -----------------------------------------------------------------------
;; Command implementations
;; -----------------------------------------------------------------------

(defun mcp-cmd-drawing-info ( / count layers layer-list)
  "Return drawing info: entity count, layers, extents."
  (setq count 0)
  (setq ent (entnext))
  (while ent
    (setq count (1+ count))
    (setq ent (entnext ent))
  )
  (setq layer-list "")
  (setq layers (tblnext "LAYER" T))
  (while layers
    (if (> (strlen layer-list) 0)
      (setq layer-list (strcat layer-list ",\"" (cdr (assoc 2 layers)) "\""))
      (setq layer-list (strcat "\"" (cdr (assoc 2 layers)) "\""))
    )
    (setq layers (tblnext "LAYER"))
  )
  (cons T (strcat "{\"entity_count\":" (itoa count) ",\"layers\":[" layer-list "]}"))
)

(defun mcp-cmd-layer-list ( / layers layer-list name)
  "Return all layers as JSON array."
  (setq layer-list "")
  (setq layers (tblnext "LAYER" T))
  (while layers
    (setq name (cdr (assoc 2 layers)))
    (if (> (strlen layer-list) 0)
      (setq layer-list (strcat layer-list ",{\"name\":\"" name "\",\"color\":" (itoa (cdr (assoc 62 layers))) "}"))
      (setq layer-list (strcat "{\"name\":\"" name "\",\"color\":" (itoa (cdr (assoc 62 layers))) "}"))
    )
    (setq layers (tblnext "LAYER"))
  )
  (cons T (strcat "{\"layers\":[" layer-list "]}"))
)

(defun mcp-cmd-layer-create (params / name color linetype)
  (setq name (mcp-json-get-string params "name"))
  (setq color (mcp-json-get-string params "color"))
  (setq linetype (mcp-json-get-string params "linetype"))
  (if (not color) (setq color "white"))
  (if (not linetype) (setq linetype "CONTINUOUS"))
  (ensure_layer_exists name color linetype)
  (cons T (strcat "{\"name\":\"" name "\"}"))
)

(defun mcp-cmd-layer-set-current (params / name)
  (setq name (mcp-json-get-string params "name"))
  (setvar "CLAYER" name)
  (cons T (strcat "{\"current_layer\":\"" name "\"}"))
)

(defun mcp-cmd-create-line (params / x1 y1 x2 y2 layer)
  (setq x1 (mcp-json-get-number params "x1"))
  (setq y1 (mcp-json-get-number params "y1"))
  (setq x2 (mcp-json-get-number params "x2"))
  (setq y2 (mcp-json-get-number params "y2"))
  (setq layer (mcp-json-get-string params "layer"))
  (if layer
    (progn (ensure_layer_exists layer "white" "CONTINUOUS") (set_current_layer layer))
  )
  (command "_LINE" (list x1 y1 0.0) (list x2 y2 0.0) "")
  (cons T (strcat "{\"entity_type\":\"LINE\",\"handle\":\"" (cdr (assoc 5 (entget (entlast)))) "\"}"))
)

(defun mcp-cmd-create-circle (params / cx cy radius layer)
  (setq cx (mcp-json-get-number params "cx"))
  (setq cy (mcp-json-get-number params "cy"))
  (setq radius (mcp-json-get-number params "radius"))
  (setq layer (mcp-json-get-string params "layer"))
  (if layer
    (progn (ensure_layer_exists layer "white" "CONTINUOUS") (set_current_layer layer))
  )
  (command "_CIRCLE" (list cx cy 0.0) radius)
  (cons T (strcat "{\"entity_type\":\"CIRCLE\",\"handle\":\"" (cdr (assoc 5 (entget (entlast)))) "\"}"))
)

(defun mcp-cmd-create-polyline (params / pts-str closed layer pairs pt-str cx cy)
  (setq pts-str (mcp-json-get-string params "points_str"))
  (setq closed (mcp-json-get-string params "closed"))
  (setq layer (mcp-json-get-string params "layer"))
  (if layer (progn (ensure_layer_exists layer "white" "CONTINUOUS") (set_current_layer layer)))
  (if (not pts-str)
    (cons nil "points_str required (format: x1,y1;x2,y2;...)")
    (progn
      (command "_PLINE")
      (setq pairs (mcp-split-string pts-str ";"))
      (foreach pt-str pairs
        (setq cx (atof (car (mcp-split-string pt-str ","))))
        (setq cy (atof (cadr (mcp-split-string pt-str ","))))
        (command (list cx cy 0.0))
      )
      (if (= closed "1") (command "_C") (command ""))
      (cons T (strcat "{\"entity_type\":\"LWPOLYLINE\",\"handle\":\""
                      (cdr (assoc 5 (entget (entlast)))) "\"}"))
    )
  )
)

(defun mcp-cmd-create-rectangle (params / x1 y1 x2 y2 layer)
  (setq x1 (mcp-json-get-number params "x1"))
  (setq y1 (mcp-json-get-number params "y1"))
  (setq x2 (mcp-json-get-number params "x2"))
  (setq y2 (mcp-json-get-number params "y2"))
  (setq layer (mcp-json-get-string params "layer"))
  (if layer
    (progn (ensure_layer_exists layer "white" "CONTINUOUS") (set_current_layer layer))
  )
  (command "_RECTANG" (list x1 y1 0.0) (list x2 y2 0.0))
  (cons T (strcat "{\"entity_type\":\"LWPOLYLINE\",\"handle\":\"" (cdr (assoc 5 (entget (entlast)))) "\"}"))
)

(defun mcp-cmd-create-text (params / x y text height rotation layer)
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq text (mcp-json-get-string params "text"))
  (setq height (mcp-json-get-number params "height"))
  (setq rotation (mcp-json-get-number params "rotation"))
  (if (not height) (setq height 2.5))
  (if (not rotation) (setq rotation 0.0))
  (setq layer (mcp-json-get-string params "layer"))
  (if layer
    (progn (ensure_layer_exists layer "white" "CONTINUOUS") (set_current_layer layer))
  )
  (command "_TEXT" "J" "M" (list x y 0.0) height rotation text)
  (cons T (strcat "{\"entity_type\":\"TEXT\",\"handle\":\"" (cdr (assoc 5 (entget (entlast)))) "\"}"))
)

(defun mcp-cmd-entity-count (params / layer count ent ent-data)
  (setq layer (mcp-json-get-string params "layer"))
  (setq count 0 ent (entnext))
  (while ent
    (setq ent-data (entget ent))
    (if (or (not layer) (= (cdr (assoc 8 ent-data)) layer))
      (setq count (1+ count))
    )
    (setq ent (entnext ent))
  )
  (cons T (strcat "{\"count\":" (itoa count) "}"))
)

(defun mcp-cmd-entity-list (params / layer entities ent ent-data etype handle elayer)
  (setq layer (mcp-json-get-string params "layer"))
  (setq entities "" ent (entnext))
  (while ent
    (setq ent-data (entget ent))
    (setq etype (cdr (assoc 0 ent-data)))
    (setq handle (cdr (assoc 5 ent-data)))
    (setq elayer (cdr (assoc 8 ent-data)))
    (if (or (not layer) (= elayer layer))
      (progn
        (if (> (strlen entities) 0)
          (setq entities (strcat entities ","))
        )
        (setq entities (strcat entities "{\"type\":\"" etype "\",\"handle\":\"" handle "\",\"layer\":\"" elayer "\"}"))
      )
    )
    (setq ent (entnext ent))
  )
  (cons T (strcat "{\"entities\":[" entities "]}"))
)

(defun mcp-cmd-entity-erase (params / entity-id ent)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (if (= entity-id "last")
    (progn
      (setq ent (entlast))
      (if ent (progn (entdel ent) (cons T "\"erased last entity\""))
        (cons nil "No entity to erase")))
    (progn
      (setq ent (handent entity-id))
      (if ent (progn (entdel ent) (cons T (strcat "\"erased " entity-id "\"")))
        (cons nil (strcat "Entity not found: " entity-id))))
  )
)

(defun mcp-cmd-entity-move (params / entity-id dx dy ent)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (setq dx (mcp-json-get-number params "dx"))
  (setq dy (mcp-json-get-number params "dy"))
  (if (= entity-id "last")
    (setq ent (entlast))
    (setq ent (handent entity-id))
  )
  (if ent
    (progn
      (command "_.MOVE" ent "" '(0 0 0) (list dx dy 0))
      (cons T "\"moved\""))
    (cons nil "Entity not found")
  )
)

;; --- Freehand LISP execution ---

(defun mcp-cmd-execute-lisp (params / code-file result old-secureload old-trusted new-trusted sanitised)
  (setq code-file (mcp-json-get-string params "code_file"))
  ;; sanitise before load
  (setq sanitised (mcp-sanitise-input code-file))
  (if (and code-file (null sanitised))
    (cons nil "sanitise rejected code_file")
    (if (not code-file)
      (cons nil "code_file parameter required")
      (if (not (findfile code-file))
        (cons nil (strcat "Code file not found: " code-file))
        (progn
          ;; TRUSTEDPATHS hardening: add IPC dir instead of SECURELOAD 0 window (M3)
          (setq old-secureload (getvar "SECURELOAD"))
          (setq old-trusted (getvar "TRUSTEDPATHS"))
          (setvar "SECURELOAD" 1)
          (setq new-trusted
            (strcat old-trusted ";"
              (let ((lp (getenv "LOCALAPPDATA")))
                (if (and lp (> (strlen lp) 0))
                  (strcat lp "\\autocad-arch-mcp\\ipc")
                  "C:\\Users\\Predator\\AppData\\Local\\autocad-arch-mcp\\ipc"
                )
              )
            )
          )
          (setvar "TRUSTEDPATHS" new-trusted)
          (setq result (vl-catch-all-apply 'load (list code-file)))
          (setvar "TRUSTEDPATHS" old-trusted)
          (setvar "SECURELOAD" old-secureload)
          (if (vl-catch-all-error-p result)
            (cons nil (strcat "LISP error: " (vl-catch-all-error-message result)))
            (cons T (strcat "\"" (mcp-escape-string (vl-princ-to-string result)) "\""))
          )
        )
      )
    )
  )
)


;; --- Drawing create implementation ---

(defun init_yqarch_layers ( / yqstart-path)
  "Re-init YQArch layers after purge. Tries yqstart.lsp in support path, then yqarch.vlx."
  (cond
    ((findfile "yqstart.lsp") (load "yqstart.lsp"))
    ((findfile "sys/yqstart.lsp") (load "sys/yqstart.lsp"))
    ((findfile "D:/SOFTWARES/YQArch/sys/yqstart.lsp") (load "D:/SOFTWARES/YQArch/sys/yqstart.lsp"))
    (T nil)
  )
  (if (and (null c:yq_wall) (findfile "yqarch.vlx")) (vl-catch-all-apply 'load (list (findfile "yqarch.vlx"))))
  (if (and (null c:yq_wall) (findfile "sys/yqarch.vlx")) (vl-catch-all-apply 'load (list (findfile "sys/yqarch.vlx"))))
  (princ "\nMCP-Arch: init_yqarch_layers checked")
  (princ)
)

(defun mcp-cmd-drawing-create (params / ss)
  "Reset current drawing to a clean state (erase all, purge, reset to layer 0, re-init YQArch).
   Using _.NEW would create a new document tab with a fresh LISP namespace,
   breaking the IPC dispatcher. This approach preserves the dispatcher."
  (if (setq ss (ssget "_X"))
    (progn (command "_.ERASE" ss "") (setq ss nil))
  )
  (setvar "CLAYER" "0")
  (command "_.-PURGE" "_ALL" "*" "_N")
  ;; Re-init YQArch layers after purge
  (init_yqarch_layers)
  (cons T (strcat "{\"drawing\":\"" (mcp-escape-string (getvar "DWGNAME")) "\"}"))
)


;; --- P&ID command implementations ---

(defun mcp-cmd-pid-insert-symbol (params / category symbol x y scale rotation)
  (setq category (mcp-json-get-string params "category"))
  (setq symbol (mcp-json-get-string params "symbol"))
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq scale (mcp-json-get-number params "scale"))
  (setq rotation (mcp-json-get-number params "rotation"))
  (if (not scale) (setq scale 1.0))
  (if (not rotation) (setq rotation 0.0))
  (if c:insert-pid-block
    (progn
      (c:insert-pid-block category symbol x y scale rotation)
      (cons T (strcat "{\"symbol\":\"" symbol "\",\"handle\":\"" (cdr (assoc 5 (entget (entlast)))) "\"}"))
    )
    (cons nil "pid_tools.lsp not loaded")
  )
)

(defun mcp-cmd-pid-draw-process-line (params / x1 y1 x2 y2)
  (setq x1 (mcp-json-get-number params "x1"))
  (setq y1 (mcp-json-get-number params "y1"))
  (setq x2 (mcp-json-get-number params "x2"))
  (setq y2 (mcp-json-get-number params "y2"))
  (if c:draw-process-line
    (progn (c:draw-process-line x1 y1 x2 y2) (cons T "\"process line drawn\""))
    (cons nil "pid_tools.lsp not loaded")
  )
)

(defun mcp-cmd-pid-connect-equipment (params / x1 y1 x2 y2)
  (setq x1 (mcp-json-get-number params "x1"))
  (setq y1 (mcp-json-get-number params "y1"))
  (setq x2 (mcp-json-get-number params "x2"))
  (setq y2 (mcp-json-get-number params "y2"))
  (if c:connect-equipment
    (progn (c:connect-equipment x1 y1 x2 y2) (cons T "\"equipment connected\""))
    (cons nil "pid_tools.lsp not loaded")
  )
)

(defun mcp-cmd-pid-add-flow-arrow (params / x y rotation)
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq rotation (mcp-json-get-number params "rotation"))
  (if (not rotation) (setq rotation 0.0))
  (if c:add-flow-arrow
    (progn (c:add-flow-arrow x y rotation) (cons T "\"flow arrow added\""))
    (cons nil "pid_tools.lsp not loaded")
  )
)

(defun mcp-cmd-pid-add-equipment-tag (params / x y tag description)
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq tag (mcp-json-get-string params "tag"))
  (setq description (mcp-json-get-string params "description"))
  (if (not description) (setq description ""))
  (if c:add-equipment-tag
    (progn (c:add-equipment-tag x y tag description) (cons T (strcat "\"tagged: " tag "\"")))
    (cons nil "pid_tools.lsp not loaded")
  )
)

(defun mcp-cmd-pid-add-line-number (params / x y line-num spec)
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq line-num (mcp-json-get-string params "line_num"))
  (setq spec (mcp-json-get-string params "spec"))
  (if c:add-line-number
    (progn (c:add-line-number x y line-num spec) (cons T (strcat "\"line number: " line-num "\"")))
    (cons nil "pid_tools.lsp not loaded")
  )
)

(defun mcp-cmd-pid-insert-valve (params / x y valve-type rotation)
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq valve-type (mcp-json-get-string params "valve_type"))
  (setq rotation (mcp-json-get-number params "rotation"))
  (if (not rotation) (setq rotation 0.0))
  (if c:insert-valve-on-line
    (progn (c:insert-valve-on-line x y valve-type rotation) (cons T (strcat "\"valve: " valve-type "\"")))
    (cons nil "pid_tools.lsp not loaded")
  )
)

(defun mcp-cmd-pid-insert-instrument (params / x y inst-type rotation tag-id range-value)
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq inst-type (mcp-json-get-string params "instrument_type"))
  (setq rotation (mcp-json-get-number params "rotation"))
  (setq tag-id (mcp-json-get-string params "tag_id"))
  (setq range-value (mcp-json-get-string params "range_value"))
  (if (not rotation) (setq rotation 0.0))
  (if c:insert-instrument
    (progn
      (c:insert-instrument x y inst-type rotation)
      (if (and tag-id (> (strlen tag-id) 0))
        (c:insert-instrument-with-tag x y inst-type tag-id (if range-value range-value ""))
      )
      (cons T (strcat "\"instrument: " inst-type "\"")))
    (cons nil "pid_tools.lsp not loaded")
  )
)

(defun mcp-cmd-pid-insert-pump (params / x y pump-type rotation)
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq pump-type (mcp-json-get-string params "pump_type"))
  (setq rotation (mcp-json-get-number params "rotation"))
  (if (not rotation) (setq rotation 0.0))
  (if c:insert-pump
    (progn (c:insert-pump x y pump-type rotation) (cons T (strcat "\"pump: " pump-type "\"")))
    (cons nil "pid_tools.lsp not loaded")
  )
)

(defun mcp-cmd-pid-insert-tank (params / x y tank-type scale)
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq tank-type (mcp-json-get-string params "tank_type"))
  (setq scale (mcp-json-get-number params "scale"))
  (if (not scale) (setq scale 1.0))
  (if c:insert-tank
    (progn (c:insert-tank x y tank-type scale) (cons T (strcat "\"tank: " tank-type "\"")))
    (cons nil "pid_tools.lsp not loaded")
  )
)

;; --- Additional entity creation ---

(defun mcp-cmd-create-arc (params / cx cy radius sa ea layer)
  (setq cx (mcp-json-get-number params "cx"))
  (setq cy (mcp-json-get-number params "cy"))
  (setq radius (mcp-json-get-number params "radius"))
  (setq sa (mcp-json-get-number params "start_angle"))
  (setq ea (mcp-json-get-number params "end_angle"))
  (setq layer (mcp-json-get-string params "layer"))
  (if layer (progn (ensure_layer_exists layer "white" "CONTINUOUS") (set_current_layer layer)))
  (command "_ARC" "_C" (list cx cy 0.0) (list (+ cx radius) cy 0.0) "_A" (- ea sa))
  (cons T (strcat "{\"entity_type\":\"ARC\",\"handle\":\"" (cdr (assoc 5 (entget (entlast)))) "\"}"))
)

(defun mcp-cmd-create-ellipse (params / cx cy mx my ratio layer)
  (setq cx (mcp-json-get-number params "cx"))
  (setq cy (mcp-json-get-number params "cy"))
  (setq mx (mcp-json-get-number params "major_x"))
  (setq my (mcp-json-get-number params "major_y"))
  (setq ratio (mcp-json-get-number params "ratio"))
  (setq layer (mcp-json-get-string params "layer"))
  (if layer (progn (ensure_layer_exists layer "white" "CONTINUOUS") (set_current_layer layer)))
  (command "_ELLIPSE" "_C" (list cx cy 0.0) (list mx my 0.0) ratio)
  (cons T (strcat "{\"entity_type\":\"ELLIPSE\",\"handle\":\"" (cdr (assoc 5 (entget (entlast)))) "\"}"))
)

(defun mcp-cmd-create-mtext (params / x y width text height layer)
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq width (mcp-json-get-number params "width"))
  (setq text (mcp-json-get-string params "text"))
  (setq height (mcp-json-get-number params "height"))
  (if (not height) (setq height 2.5))
  (setq layer (mcp-json-get-string params "layer"))
  (if layer (progn (ensure_layer_exists layer "white" "CONTINUOUS") (set_current_layer layer)))
  (command "_MTEXT" (list x y 0.0) "_H" height "_W" width text "")
  (cons T (strcat "{\"entity_type\":\"MTEXT\",\"handle\":\"" (cdr (assoc 5 (entget (entlast)))) "\"}"))
)

(defun mcp-cmd-create-hatch (params / entity-id pattern ent)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (setq pattern (mcp-json-get-string params "pattern"))
  (if (not pattern) (setq pattern "ANSI31"))
  (if (= entity-id "last")
    (setq ent (entlast))
    (setq ent (handent entity-id))
  )
  (if ent
    (progn
      (command "_HATCH" "_P" pattern "" "_S" ent "" "")
      (cons T (strcat "{\"entity_type\":\"HATCH\",\"handle\":\"" (cdr (assoc 5 (entget (entlast)))) "\"}")))
    (cons nil "Entity not found for hatching")
  )
)

;; --- Entity query: get ---

(defun mcp-cmd-entity-get (params / entity-id ent ent-data etype handle elayer result)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (if (= entity-id "last")
    (setq ent (entlast))
    (setq ent (handent entity-id))
  )
  (if (not ent)
    (cons nil (strcat "Entity not found: " entity-id))
    (progn
      (setq ent-data (entget ent))
      (setq etype (cdr (assoc 0 ent-data)))
      (setq handle (cdr (assoc 5 ent-data)))
      (setq elayer (cdr (assoc 8 ent-data)))
      (setq result (strcat "{\"type\":\"" etype "\",\"handle\":\"" handle "\",\"layer\":\"" elayer "\""))
      ;; Add type-specific info
      (cond
        ((= etype "LINE")
         (setq result (strcat result
           ",\"start\":[" (rtos (car (cdr (assoc 10 ent-data))) 2 6) "," (rtos (cadr (cdr (assoc 10 ent-data))) 2 6) "]"
           ",\"end\":[" (rtos (car (cdr (assoc 11 ent-data))) 2 6) "," (rtos (cadr (cdr (assoc 11 ent-data))) 2 6) "]")))
        ((= etype "CIRCLE")
         (setq result (strcat result
           ",\"center\":[" (rtos (car (cdr (assoc 10 ent-data))) 2 6) "," (rtos (cadr (cdr (assoc 10 ent-data))) 2 6) "]"
           ",\"radius\":" (rtos (cdr (assoc 40 ent-data)) 2 6))))
      )
      (setq result (strcat result "}"))
      (cons T result)
    )
  )
)

;; --- Entity modification commands ---

(defun mcp-cmd-entity-copy (params / entity-id dx dy ent new-handle)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (setq dx (mcp-json-get-number params "dx"))
  (setq dy (mcp-json-get-number params "dy"))
  (if (= entity-id "last") (setq ent (entlast)) (setq ent (handent entity-id)))
  (if ent
    (progn
      (command "_.COPY" ent "" '(0 0 0) (list dx dy 0))
      (setq new-handle (cdr (assoc 5 (entget (entlast)))))
      (cons T (strcat "{\"handle\":\"" new-handle "\"}")))
    (cons nil "Entity not found")
  )
)

(defun mcp-cmd-entity-rotate (params / entity-id cx cy angle ent)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (setq cx (mcp-json-get-number params "cx"))
  (setq cy (mcp-json-get-number params "cy"))
  (setq angle (mcp-json-get-number params "angle"))
  (if (= entity-id "last") (setq ent (entlast)) (setq ent (handent entity-id)))
  (if ent
    (progn (command "_.ROTATE" ent "" (list cx cy 0) angle) (cons T "\"rotated\""))
    (cons nil "Entity not found")
  )
)

(defun mcp-cmd-entity-scale (params / entity-id cx cy factor ent)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (setq cx (mcp-json-get-number params "cx"))
  (setq cy (mcp-json-get-number params "cy"))
  (setq factor (mcp-json-get-number params "factor"))
  (if (= entity-id "last") (setq ent (entlast)) (setq ent (handent entity-id)))
  (if ent
    (progn (command "_.SCALE" ent "" (list cx cy 0) factor) (cons T "\"scaled\""))
    (cons nil "Entity not found")
  )
)

(defun mcp-cmd-entity-mirror (params / entity-id x1 y1 x2 y2 ent new-handle)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (setq x1 (mcp-json-get-number params "x1"))
  (setq y1 (mcp-json-get-number params "y1"))
  (setq x2 (mcp-json-get-number params "x2"))
  (setq y2 (mcp-json-get-number params "y2"))
  (if (= entity-id "last") (setq ent (entlast)) (setq ent (handent entity-id)))
  (if ent
    (progn
      (command "_.MIRROR" ent "" (list x1 y1 0) (list x2 y2 0) "_N")
      (setq new-handle (cdr (assoc 5 (entget (entlast)))))
      (cons T (strcat "{\"handle\":\"" new-handle "\"}")))
    (cons nil "Entity not found")
  )
)

(defun mcp-cmd-entity-offset (params / entity-id distance ent new-handle)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (setq distance (mcp-json-get-number params "distance"))
  (if (= entity-id "last") (setq ent (entlast)) (setq ent (handent entity-id)))
  (if ent
    (progn
      (command "_.OFFSET" distance ent (list 0 0 0) "")
      (setq new-handle (cdr (assoc 5 (entget (entlast)))))
      (cons T (strcat "{\"handle\":\"" new-handle "\"}")))
    (cons nil "Entity not found")
  )
)

(defun mcp-cmd-entity-array (params / entity-id rows cols row-dist col-dist ent)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (setq rows (fix (mcp-json-get-number params "rows")))
  (setq cols (fix (mcp-json-get-number params "cols")))
  (setq row-dist (mcp-json-get-number params "row_dist"))
  (setq col-dist (mcp-json-get-number params "col_dist"))
  (if (= entity-id "last") (setq ent (entlast)) (setq ent (handent entity-id)))
  (if ent
    (progn
      (command "_.ARRAY" ent "" "_R" rows cols row-dist col-dist)
      (cons T (strcat "{\"rows\":" (itoa rows) ",\"cols\":" (itoa cols) "}")))
    (cons nil "Entity not found")
  )
)

(defun mcp-cmd-entity-fillet (params / id1 id2 radius ent1 ent2)
  (setq id1 (mcp-json-get-string params "id1"))
  (setq id2 (mcp-json-get-string params "id2"))
  (setq radius (mcp-json-get-number params "radius"))
  (setq ent1 (handent id1))
  (setq ent2 (handent id2))
  (if (and ent1 ent2)
    (progn
      (command "_.FILLET" "_R" radius)
      (command "_.FILLET" ent1 ent2)
      (cons T "\"filleted\""))
    (cons nil "One or both entities not found")
  )
)

(defun mcp-cmd-entity-chamfer (params / id1 id2 dist1 dist2 ent1 ent2)
  (setq id1 (mcp-json-get-string params "id1"))
  (setq id2 (mcp-json-get-string params "id2"))
  (setq dist1 (mcp-json-get-number params "dist1"))
  (setq dist2 (mcp-json-get-number params "dist2"))
  (setq ent1 (handent id1))
  (setq ent2 (handent id2))
  (if (and ent1 ent2)
    (progn
      (command "_.CHAMFER" "_D" dist1 dist2)
      (command "_.CHAMFER" ent1 ent2)
      (cons T "\"chamfered\""))
    (cons nil "One or both entities not found")
  )
)

;; --- Layer operations ---

(defun mcp-cmd-layer-set-properties (params / name color linetype lineweight)
  (setq name (mcp-json-get-string params "name"))
  (setq color (mcp-json-get-string params "color"))
  (setq linetype (mcp-json-get-string params "linetype"))
  (setq lineweight (mcp-json-get-string params "lineweight"))
  (if color (command "_.-LAYER" "_COLOR" color name ""))
  (if linetype (command "_.-LAYER" "_LTYPE" linetype name ""))
  (if lineweight (command "_.-LAYER" "_LWEIGHT" lineweight name ""))
  (cons T (strcat "{\"name\":\"" name "\"}"))
)

(defun mcp-cmd-layer-freeze (params / name)
  (setq name (mcp-json-get-string params "name"))
  (command "_.-LAYER" "_FREEZE" name "")
  (cons T (strcat "{\"name\":\"" name "\",\"frozen\":true}"))
)

(defun mcp-cmd-layer-thaw (params / name)
  (setq name (mcp-json-get-string params "name"))
  (command "_.-LAYER" "_THAW" name "")
  (cons T (strcat "{\"name\":\"" name "\",\"frozen\":false}"))
)

(defun mcp-cmd-layer-lock (params / name)
  (setq name (mcp-json-get-string params "name"))
  (command "_.-LAYER" "_LOCK" name "")
  (cons T (strcat "{\"name\":\"" name "\",\"locked\":true}"))
)

(defun mcp-cmd-layer-unlock (params / name)
  (setq name (mcp-json-get-string params "name"))
  (command "_.-LAYER" "_UNLOCK" name "")
  (cons T (strcat "{\"name\":\"" name "\",\"locked\":false}"))
)

;; --- Block operations (insert-with-attributes, get-attributes, update-attribute) ---

(defun mcp-cmd-block-insert-with-attribs (params / name x y scale rotation attributes ent)
  (setq name (mcp-json-get-string params "name"))
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq scale (mcp-json-get-number params "scale"))
  (setq rotation (mcp-json-get-number params "rotation"))
  (if (not scale) (setq scale 1.0))
  (if (not rotation) (setq rotation 0.0))
  (if (tblsearch "BLOCK" name)
    (progn
      ;; Insert with ATTREQ=1 to fill attributes
      (command "_.INSERT" name (list x y 0.0) scale scale rotation)
      ;; Note: attribute values are applied separately via update-attribute
      (cons T (strcat "{\"entity_type\":\"INSERT\",\"handle\":\"" (cdr (assoc 5 (entget (entlast)))) "\"}")))
    (cons nil (strcat "Block '" name "' not found"))
  )
)

(defun mcp-cmd-block-get-attributes (params / entity-id ent sub-ent ent-data attribs)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (if (= entity-id "last") (setq ent (entlast)) (setq ent (handent entity-id)))
  (if (not ent)
    (cons nil "Entity not found")
    (progn
      (setq attribs "" sub-ent (entnext ent))
      (while sub-ent
        (setq ent-data (entget sub-ent))
        (if (= (cdr (assoc 0 ent-data)) "ATTRIB")
          (progn
            (if (> (strlen attribs) 0) (setq attribs (strcat attribs ",")))
            (setq attribs (strcat attribs "\"" (cdr (assoc 2 ent-data)) "\":\"" (mcp-escape-string (cdr (assoc 1 ent-data))) "\""))
          )
        )
        (if (= (cdr (assoc 0 ent-data)) "SEQEND")
          (setq sub-ent nil)
          (setq sub-ent (entnext sub-ent))
        )
      )
      (cons T (strcat "{\"attributes\":{" attribs "}}"))
    )
  )
)

(defun mcp-cmd-block-update-attribute (params / entity-id tag value ent)
  (setq entity-id (mcp-json-get-string params "entity_id"))
  (setq tag (mcp-json-get-string params "tag"))
  (setq value (mcp-json-get-string params "value"))
  (if (= entity-id "last") (setq ent (entlast)) (setq ent (handent entity-id)))
  (if (not ent)
    (cons nil "Entity not found")
    (progn
      (if c:update-block-attribute
        (progn (c:update-block-attribute ent tag value)
               (cons T (strcat "{\"tag\":\"" tag "\",\"value\":\"" (mcp-escape-string value) "\"}")))
        ;; Inline fallback if attribute_tools.lsp not loaded
        (progn
          (set_attribute_value ent tag value)
          (cons T (strcat "{\"tag\":\"" tag "\",\"value\":\"" (mcp-escape-string value) "\"}")))
      )
    )
  )
)

;; --- Annotation commands ---

(defun mcp-cmd-create-dimension-linear (params / x1 y1 x2 y2 dim-x dim-y)
  (setq x1 (mcp-json-get-number params "x1"))
  (setq y1 (mcp-json-get-number params "y1"))
  (setq x2 (mcp-json-get-number params "x2"))
  (setq y2 (mcp-json-get-number params "y2"))
  (setq dim-x (mcp-json-get-number params "dim_x"))
  (setq dim-y (mcp-json-get-number params "dim_y"))
  (command "_.DIMLINEAR" (list x1 y1 0) (list x2 y2 0) (list dim-x dim-y 0))
  (cons T "{\"entity_type\":\"DIMENSION\"}")
)

(defun mcp-cmd-create-dimension-aligned (params / x1 y1 x2 y2 offset)
  (setq x1 (mcp-json-get-number params "x1"))
  (setq y1 (mcp-json-get-number params "y1"))
  (setq x2 (mcp-json-get-number params "x2"))
  (setq y2 (mcp-json-get-number params "y2"))
  (setq offset (mcp-json-get-number params "offset"))
  ;; Place dimension line at offset distance
  (command "_.DIMALIGNED" (list x1 y1 0) (list x2 y2 0)
    (list (+ (/ (+ x1 x2) 2.0) offset) (+ (/ (+ y1 y2) 2.0) offset) 0))
  (cons T "{\"entity_type\":\"DIMENSION\"}")
)

(defun mcp-cmd-create-dimension-angular (params / cx cy x1 y1 x2 y2)
  (setq cx (mcp-json-get-number params "cx"))
  (setq cy (mcp-json-get-number params "cy"))
  (setq x1 (mcp-json-get-number params "x1"))
  (setq y1 (mcp-json-get-number params "y1"))
  (setq x2 (mcp-json-get-number params "x2"))
  (setq y2 (mcp-json-get-number params "y2"))
  (command "_.DIMANGULAR" (list cx cy 0) (list x1 y1 0) (list x2 y2 0) "")
  (cons T "{\"entity_type\":\"DIMENSION\"}")
)

(defun mcp-cmd-create-dimension-radius (params / cx cy radius angle px py)
  (setq cx (mcp-json-get-number params "cx"))
  (setq cy (mcp-json-get-number params "cy"))
  (setq radius (mcp-json-get-number params "radius"))
  (setq angle (mcp-json-get-number params "angle"))
  ;; Need a circle/arc entity first, use entity at center
  (setq px (+ cx (* radius (cos (* angle (/ pi 180.0))))))
  (setq py (+ cy (* radius (sin (* angle (/ pi 180.0))))))
  (command "_.DIMRADIUS" (list px py 0) "")
  (cons T "{\"entity_type\":\"DIMENSION\"}")
)

(defun mcp-cmd-create-leader (params / text pts-str pairs pt-str)
  (setq text (mcp-json-get-string params "text"))
  (setq pts-str (mcp-json-get-string params "points_str"))
  (if (not pts-str)
    (cons nil "points_str required (format: x1,y1;x2,y2;...)")
    (progn
      (command "_.LEADER")
      (setq pairs (mcp-split-string pts-str ";"))
      (foreach pt-str pairs
        (command (list (atof (car (mcp-split-string pt-str ",")))
                       (atof (cadr (mcp-split-string pt-str ","))) 0))
      )
      (command "" text "")
      (cons T "{\"entity_type\":\"LEADER\"}")
    )
  )
)

;; --- Drawing management ---

(defun mcp-cmd-drawing-get-variables (params / names-str result var-list var-name var-val first-var)
  (setq names-str (mcp-json-get-string params "names_str"))
  (if (or (not names-str) (= names-str ""))
    ;; Default set when no specific names requested
    (progn
      (setq result "{")
      (setq result (strcat result "\"ACADVER\":\"" (getvar "ACADVER") "\""))
      (setq result (strcat result ",\"DWGNAME\":\"" (mcp-escape-string (getvar "DWGNAME")) "\""))
      (setq result (strcat result ",\"CLAYER\":\"" (getvar "CLAYER") "\""))
      (setq result (strcat result "}"))
      (cons T result)
    )
    ;; Parse semicolon-delimited variable names
    (progn
      (setq var-list (mcp-split-string names-str ";"))
      (setq result "{" first-var T)
      (foreach var-name var-list
        (setq var-val (getvar var-name))
        (if (not first-var) (setq result (strcat result ",")))
        (setq first-var nil)
        (if (not var-val)
          (setq result (strcat result "\"" var-name "\":null"))
          (cond
            ((= (type var-val) 'STR)
             (setq result (strcat result "\"" var-name "\":\"" (mcp-escape-string var-val) "\"")))
            ((= (type var-val) 'INT)
             (setq result (strcat result "\"" var-name "\":" (itoa var-val))))
            ((= (type var-val) 'REAL)
             (setq result (strcat result "\"" var-name "\":" (rtos var-val 2 6))))
            (t
             (setq result (strcat result "\"" var-name "\":\"" (mcp-escape-string (vl-princ-to-string var-val)) "\"")))
          )
        )
      )
      (setq result (strcat result "}"))
      (cons T result)
    )
  )
)

(defun mcp-cmd-drawing-plot-pdf (params / path)
  (setq path (mcp-json-get-string params "path"))
  (if path
    (progn
      (command "_.-PLOT" "_Y" "" "DWG To PDF.pc3"
        "ANSI_A_(8.50_x_11.00_Inches)" "_Inches" "_Landscape"
        "_N" "_Extents" "_Fit" "_Y" "acad.ctb" "_Y" "_N" "_Y" path "_Y")
      (cons T (strcat "{\"path\":\"" (mcp-escape-string path) "\"}")))
    (cons nil "Plot path required")
  )
)

;; --- P&ID list symbols ---

(defun mcp-cmd-pid-list-symbols (params / category dir-path files result)
  (setq category (mcp-json-get-string params "category"))
  (setq dir-path (strcat "C:/PIDv4-CTO/" category "/"))
  (setq files (vl-directory-files dir-path "*.dwg" 1))
  (setq result "")
  (if files
    (foreach f files
      (if (> (strlen result) 0) (setq result (strcat result ",")))
      ;; Remove .dwg extension
      (setq result (strcat result "\"" (substr f 1 (- (strlen f) 4)) "\""))
    )
  )
  (cons T (strcat "{\"category\":\"" category "\",\"symbols\":[" result "],\"count\":" (itoa (length (if files files '()))) "}"))
)

;; --- Block operations ---

(defun mcp-cmd-block-list ( / blk block-list)
  (setq block-list "" blk (tblnext "BLOCK" T))
  (while blk
    (if (not (= (substr (cdr (assoc 2 blk)) 1 1) "*"))
      (progn
        (if (> (strlen block-list) 0)
          (setq block-list (strcat block-list ",\"" (cdr (assoc 2 blk)) "\""))
          (setq block-list (strcat "\"" (cdr (assoc 2 blk)) "\""))
        )
      )
    )
    (setq blk (tblnext "BLOCK"))
  )
  (cons T (strcat "{\"blocks\":[" block-list "]}"))
)

(defun mcp-cmd-block-insert (params / name x y scale rotation block-id)
  (setq name (mcp-json-get-string params "name"))
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq scale (mcp-json-get-number params "scale"))
  (setq rotation (mcp-json-get-number params "rotation"))
  (setq block-id (mcp-json-get-string params "block_id"))
  (if (not scale) (setq scale 1.0))
  (if (not rotation) (setq rotation 0.0))
  (if (tblsearch "BLOCK" name)
    (progn
      (command "_.INSERT" name (list x y 0.0) scale scale rotation)
      (if (and block-id (> (strlen block-id) 0))
        (set_attribute_value (entlast) "ID" block-id)
      )
      (cons T (strcat "{\"entity_type\":\"INSERT\",\"handle\":\"" (cdr (assoc 5 (entget (entlast)))) "\"}"))
    )
    (cons nil (strcat "Block '" name "' not found"))
  )
)


;; -----------------------------------------------------------------------
;; YQArch NBC wrappers — whitelist implementations (ACP sanitised, undo-marked)
;; -----------------------------------------------------------------------

(defun mcp-cmd-yq-wall (params / x1 y1 x2 y2 thickness layer sanitised result old-layer)
  "YQArch wall via YQ_WALL (ww). Sets CLAYER WALL, uses _BEgin/_End, TRUSTEDPATHS already set, vl-catch-all-apply."
  (setq x1 (mcp-json-get-number params "x1"))
  (setq y1 (mcp-json-get-number params "y1"))
  (setq x2 (mcp-json-get-number params "x2"))
  (setq y2 (mcp-json-get-number params "y2"))
  (setq thickness (mcp-json-get-number params "thickness"))
  (setq layer (mcp-json-get-string params "layer"))
  (if (and layer (null (mcp-sanitise-input layer)))
    (cons nil "sanitise rejected layer")
    (progn
      (command "_.UNDO" "_BEgin")
      (setq old-layer (getvar "CLAYER"))
      (if layer
        (progn (ensure_layer_exists (mcp-sanitise-input layer) "white" "CONTINUOUS") (setvar "CLAYER" layer))
        (progn (ensure_layer_exists "WALL" "80" "CONTINUOUS") (setvar "CLAYER" "WALL"))
      )
      (setq result (vl-catch-all-apply
        '(lambda ()
           (cond
             (c:yq_wall (c:yq_wall (list x1 y1 0) (list x2 y2 0)))
             ((findfile "yqarch.vlx") (command "_.YQ_WALL" (list x1 y1 0) (list x2 y2 0) ""))
             (T (command "_LINE" (list x1 y1 0) (list x2 y2 0) "")) ; fallback entmake
           )
         )
      ))
      (if (vl-catch-all-error-p result)
        (progn (command "_.UNDO" "_End") (command "_.UNDO" "1") (setvar "CLAYER" old-layer) (cons nil (strcat "yq_wall error: " (vl-catch-all-error-message result))))
        (progn (command "_.UNDO" "_End") (setvar "CLAYER" old-layer) (cons T (strcat "{\"wall\":{\"x1\":" (rtos x1 2 2) ",\"y1\":" (rtos y1 2 2) ",\"x2\":" (rtos x2 2 2) ",\"y2\":" (rtos y2 2 2) "}}")))
      )
    )
  )
)

(defun mcp-cmd-yq-hole-door (params / x y width height layer sanitised result old-layer)
  "YQArch door hole via YQ_HOLE_DOOR (ad). CLAYER DOOR, undo-marked."
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq width (mcp-json-get-number params "width"))
  (setq height (mcp-json-get-number params "height"))
  (if (null width) (setq width 900))
  (if (null height) (setq height 2100))
  (setq layer (mcp-json-get-string params "layer"))
  (if (and layer (null (mcp-sanitise-input layer)))
    (cons nil "sanitise rejected layer")
    (progn
      (command "_.UNDO" "_BEgin")
      (setq old-layer (getvar "CLAYER"))
      (ensure_layer_exists "DOOR" "2" "CONTINUOUS") (setvar "CLAYER" "DOOR")
      (setq result (vl-catch-all-apply
        '(lambda ()
           (cond
             (c:yq_hole_door (c:yq_hole_door (list x y 0) width))
             ((findfile "yqarch.vlx") (command "_.YQ_HOLE_DOOR" (list x y 0) width ""))
             (T (command "_RECTANG" (list x y 0) (list (+ x width) (+ y height) 0)))
           )
         )
      ))
      (if (vl-catch-all-error-p result)
        (progn (command "_.UNDO" "_End") (command "_.UNDO" "1") (setvar "CLAYER" old-layer) (cons nil (strcat "yq_hole_door error: " (vl-catch-all-error-message result))))
        (progn (command "_.UNDO" "_End") (setvar "CLAYER" old-layer) (cons T (strcat "{\"door\":{\"x\":" (rtos x 2 2) ",\"width\":" (itoa (fix width)) "}}")))
      )
    )
  )
)

(defun mcp-cmd-yq-hole-window (params / x y width height sill layer result old-layer)
  "YQArch window hole via YQ_HOLE_WIN (aw) / YQ_HOLE_WINDOW (wd). CLAYER WINDOW, undo-marked."
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq width (mcp-json-get-number params "width"))
  (setq height (mcp-json-get-number params "height"))
  (setq sill (mcp-json-get-number params "sill"))
  (if (null width) (setq width 1500))
  (if (null height) (setq height 1200))
  (setq layer (mcp-json-get-string params "layer"))
  (if (and layer (null (mcp-sanitise-input layer)))
    (cons nil "sanitise rejected layer")
    (progn
      (command "_.UNDO" "_BEgin")
      (setq old-layer (getvar "CLAYER"))
      (ensure_layer_exists "WINDOW" "2" "CONTINUOUS") (setvar "CLAYER" "WINDOW")
      (setq result (vl-catch-all-apply
        '(lambda ()
           (cond
             (c:yq_hole_win (c:yq_hole_win (list x y 0) width))
             (c:yq_hole_window (c:yq_hole_window (list x y 0) width height))
             ((findfile "yqarch.vlx") (command "_.YQ_HOLE_WIN" (list x y 0) width ""))
             (T (command "_RECTANG" (list x y 0) (list (+ x width) (+ y height) 0)))
           )
         )
      ))
      (if (vl-catch-all-error-p result)
        (progn (command "_.UNDO" "_End") (command "_.UNDO" "1") (setvar "CLAYER" old-layer) (cons nil (strcat "yq_hole_window error: " (vl-catch-all-error-message result))))
        (progn (command "_.UNDO" "_End") (setvar "CLAYER" old-layer) (cons T (strcat "{\"window\":{\"x\":" (rtos x 2 2) ",\"width\":" (itoa (fix width)) "}}")))
      )
    )
  )
)

(defun mcp-cmd-yq-hole (params / x y w h layer result old-layer)
  "Generic YQArch hole (ho) — fallback rect if YQ not loaded."
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq w (mcp-json-get-number params "width"))
  (setq h (mcp-json-get-number params "height"))
  (if (null w) (setq w 900)) (if (null h) (setq h 2100))
  (command "_.UNDO" "_BEgin")
  (setq old-layer (getvar "CLAYER"))
  (ensure_layer_exists "DOOR" "2" "CONTINUOUS") (setvar "CLAYER" "DOOR")
  (setq result (vl-catch-all-apply '(lambda () (if c:yq_hole (c:yq_hole (list x y 0) w) (command "_RECTANG" (list x y 0) (list (+ x w) (+ y h) 0))))))
  (if (vl-catch-all-error-p result)
    (progn (command "_.UNDO" "_End") (command "_.UNDO" "1") (setvar "CLAYER" old-layer) (cons nil (vl-catch-all-error-message result)))
    (progn (command "_.UNDO" "_End") (setvar "CLAYER" old-layer) (cons T (strcat "{\"hole\":{\"x\":" (rtos x 2 2) "}}")))
  )
)

(defun mcp-cmd-yq-trim-wall (params / x1 y1 x2 y2 result)
  "YQArch trim-fix wall (tw) — YQ_TRIM_FIX_WALL."
  (setq x1 (mcp-json-get-number params "x1"))
  (setq y1 (mcp-json-get-number params "y1"))
  (setq x2 (mcp-json-get-number params "x2"))
  (setq y2 (mcp-json-get-number params "y2"))
  (command "_.UNDO" "_BEgin")
  (setq result (vl-catch-all-apply '(lambda () (if c:yq_trim_fix_wall (c:yq_trim_fix_wall (list x1 y1 0) (list x2 y2 0)) (command "_.TRIM" (list x1 y1 0) "" (list x2 y2 0) "")))))
  (if (vl-catch-all-error-p result)
    (progn (command "_.UNDO" "_End") (command "_.UNDO" "1") (cons nil (vl-catch-all-error-message result)))
    (progn (command "_.UNDO" "_End") (cons T "\"trim done\""))
  )
)

(defun mcp-cmd-yq-width-windoor (params / id width result ent)
  "YQArch width windoor (cw) — YQ_WIDTH_WINDOOR."
  (setq id (mcp-json-get-string params "entity_id"))
  (setq width (mcp-json-get-number params "width"))
  (if (= id "last") (setq ent (entlast)) (setq ent (handent id)))
  (command "_.UNDO" "_BEgin")
  (setq result (vl-catch-all-apply '(lambda () (if c:yq_width_windoor (c:yq_width_windoor ent width) (cons nil "YQArch not loaded")))))
  (if (vl-catch-all-error-p result)
    (progn (command "_.UNDO" "_End") (command "_.UNDO" "1") (cons nil (vl-catch-all-error-message result)))
    (progn (command "_.UNDO" "_End") (cons T (strcat "{\"width\":" (itoa (fix width)) "}")))
  )
)

(defun mcp-cmd-yq-move-windoor (params / id dx dy result ent)
  "YQArch move windoor (vw) — YQ_MOVE_WINDOOR."
  (setq id (mcp-json-get-string params "entity_id"))
  (setq dx (mcp-json-get-number params "dx"))
  (setq dy (mcp-json-get-number params "dy"))
  (if (= id "last") (setq ent (entlast)) (setq ent (handent id)))
  (command "_.UNDO" "_BEgin")
  (setq result (vl-catch-all-apply '(lambda () (if c:yq_move_windoor (c:yq_move_windoor ent (list dx dy 0)) (command "_.MOVE" ent "" '(0 0 0) (list dx dy 0))))))
  (if (vl-catch-all-error-p result)
    (progn (command "_.UNDO" "_End") (command "_.UNDO" "1") (cons nil (vl-catch-all-error-message result)))
    (progn (command "_.UNDO" "_End") (cons T "\"moved windoor\""))
  )
)

(defun mcp-cmd-yq-repair (params / result)
  "YQArch repair (xf) — YQ_REPAIR, fixes wall intersections."
  (command "_.UNDO" "_BEgin")
  (setq result (vl-catch-all-apply '(lambda () (if c:yq_repair (c:yq_repair) (command "_.YQ_REPAIR" "")))))
  (if (vl-catch-all-error-p result)
    (progn (command "_.UNDO" "_End") (command "_.UNDO" "1") (cons nil (vl-catch-all-error-message result)))
    (progn (command "_.UNDO" "_End") (cons T "\"repaired\""))
  )
)

(defun mcp-cmd-yq-bg (params / level layer result)
  "YQArch section levels (bg) — YQ_BG_SECTION_LEVELS."
  (setq level (mcp-json-get-number params "level"))
  (setq layer (mcp-json-get-string params "layer"))
  (if (null level) (setq level 0))
  (command "_.UNDO" "_BEgin")
  (if layer (progn (ensure_layer_exists layer "white" "CONTINUOUS") (setvar "CLAYER" layer)) (progn (ensure_layer_exists "SILL" "8" "CONTINUOUS") (setvar "CLAYER" "SILL")))
  (setq result (vl-catch-all-apply '(lambda () (if c:yq_bg (c:yq_bg level) (if c:yq_bg_section_levels (c:yq_bg_section_levels level) (command "_.YQ_BG" level ""))))))
  (if (vl-catch-all-error-p result)
    (progn (command "_.UNDO" "_End") (command "_.UNDO" "1") (cons nil (vl-catch-all-error-message result)))
    (progn (command "_.UNDO" "_End") (cons T (strcat "{\"bg_level\":" (rtos level 2 2) "}")))
  )
)

(defun mcp-cmd-yq-stair (params / x y width length layer result old-layer)
  "YQArch staircase plan (ltj) — YQ_STAIRCASE_PLAN."
  (setq x (mcp-json-get-number params "x"))
  (setq y (mcp-json-get-number params "y"))
  (setq width (mcp-json-get-number params "width"))
  (setq length (mcp-json-get-number params "length"))
  (if (null width) (setq width 1200)) (if (null length) (setq length 3000))
  (command "_.UNDO" "_BEgin")
  (setq old-layer (getvar "CLAYER"))
  (ensure_layer_exists "STAIR" "2" "CONTINUOUS") (setvar "CLAYER" "STAIR")
  (setq result (vl-catch-all-apply '(lambda () (if c:yq_staircase_plan (c:yq_staircase_plan (list x y 0) width length) (command "_.YQ_STAIRCASE_PLAN" (list x y 0) width length "")))))
  (if (vl-catch-all-error-p result)
    (progn (command "_.UNDO" "_End") (command "_.UNDO" "1") (setvar "CLAYER" old-layer) (cons nil (vl-catch-all-error-message result)))
    (progn (command "_.UNDO" "_End") (setvar "CLAYER" old-layer) (cons T (strcat "{\"stair\":{\"x\":" (rtos x 2 2) ",\"width\":" (itoa (fix width)) "}}")))
  )
)

(defun mcp-cmd-create-quick-dim (params / p1s p2s layer result)
  "Quick wall dimension (DDZ) — quick_dim_wall via YQArch or DIMALIGNED fallback, undo-marked."
  (setq p1s (mcp-json-get-string params "p1"))
  (setq p2s (mcp-json-get-string params "p2"))
  (setq layer (mcp-json-get-string params "layer"))
  (command "_.UNDO" "_BEgin")
  (if layer (progn (ensure_layer_exists layer "white" "CONTINUOUS") (setvar "CLAYER" layer)) (progn (ensure_layer_exists "A-DIM" "3" "CONTINUOUS") (setvar "CLAYER" "A-DIM")))
  (setq result (vl-catch-all-apply '(lambda ()
    (cond
      (c:quick_dim_wall (c:quick_dim_wall))
      (c:yq_axis_to_dim (c:yq_axis_to_dim))
      (T (command "_.DIMALIGNED" '(0 0 0) '(3000 0 0) '(1500 500 0)))
    )
  )))
  (if (vl-catch-all-error-p result)
    (progn (command "_.UNDO" "_End") (command "_.UNDO" "1") (cons nil (vl-catch-all-error-message result)))
    (progn (command "_.UNDO" "_End") (cons T "{\"dim\":\"quick\"}"))
  )
)


;; -----------------------------------------------------------------------
;; Main dispatcher — called by "(c:mcp-dispatch)" from Python
;; -----------------------------------------------------------------------

(defun c:mcp-arch-dispatch ( / cmd-files cmd-file json-text request-id cmd-name params-str result result-file)
  "Find pending command file, dispatch, write result."
  ;; Find first pending command file
  (setq cmd-files (vl-directory-files *mcp-arch-ipc-dir* "autocad_arch_cmd_*.json" 1))
  (if (not cmd-files)
    (progn (princ "\nMCP: No pending commands") (princ))
    (progn
      ;; Process first command
      (setq cmd-file (strcat *mcp-arch-ipc-dir* (car cmd-files)))
      (setq json-text (mcp-read-file-lines cmd-file))

      (if (not json-text)
        (princ "\nMCP: Cannot read command file")
        (progn
          ;; Parse command
          (setq request-id (mcp-json-get-string json-text "request_id"))
          (setq cmd-name (mcp-json-get-string json-text "command"))

          (if (not cmd-name)
            (princ "\nMCP: No command in payload")
            (progn
              (princ (strcat "\nMCP: Dispatching " cmd-name " [" request-id "]"))

              ;; Execute via whitelist dispatcher
              (setq result
                (vl-catch-all-apply
                  'mcp-dispatch-command
                  (list cmd-name json-text)
                )
              )

              ;; Handle error from vl-catch-all-apply
              (if (vl-catch-all-error-p result)
                (setq result (cons nil (vl-catch-all-error-message result)))
              )

              ;; Write result
              (setq result-file (strcat *mcp-arch-ipc-dir* "autocad_arch_result_" request-id ".json"))
              (if (car result)
                (mcp-write-result result-file request-id T (cdr result) nil)
                (mcp-write-result result-file request-id nil nil (cdr result))
              )

              (princ (strcat "\nMCP: Done " cmd-name))
            )
          )

          ;; Clean up command file
          (vl-file-delete cmd-file)
        )
      )
    )
  )
  (princ)
)

;; Compat alias — old name from autocad-mcp
(defun c:mcp-dispatch () (c:mcp-arch-dispatch))

;; -----------------------------------------------------------------------
;; Utility helpers (defined if not already loaded from external files)
;; -----------------------------------------------------------------------

(if (not ensure_layer_exists)
  (defun ensure_layer_exists (name color linetype)
    "Create layer if it doesn't exist."
    (if (not (tblsearch "LAYER" name))
      (command "_.-LAYER" "_NEW" name "_COLOR" color name "_LTYPE" linetype name "")
    )
  )
)

(if (not set_current_layer)
  (defun set_current_layer (name)
    "Set a layer as current."
    (setvar "CLAYER" name)
  )
)

(if (not set_attribute_value)
  (defun set_attribute_value (ent tag value / sub-ent ent-data)
    "Set an attribute value on a block insert by tag name."
    (setq sub-ent (entnext ent))
    (while sub-ent
      (setq ent-data (entget sub-ent))
      (if (and (= (cdr (assoc 0 ent-data)) "ATTRIB")
               (= (strcase (cdr (assoc 2 ent-data))) (strcase tag)))
        (progn
          (entmod (subst (cons 1 value) (assoc 1 ent-data) ent-data))
          (entupd sub-ent)
          (setq sub-ent nil)  ; stop
        )
        (if (= (cdr (assoc 0 ent-data)) "SEQEND")
          (setq sub-ent nil)
          (setq sub-ent (entnext sub-ent))
        )
      )
    )
  )
)

;; -----------------------------------------------------------------------
;; Startup message
;; -----------------------------------------------------------------------

(princ "\n=== MCP Arch Dispatch v1.0 loaded ===")
(princ "\nIPC directory: ")
(princ *mcp-arch-ipc-dir*)
(princ "\nReady for commands via (c:mcp-arch-dispatch)  [alias c:mcp-dispatch]")
(princ)
