using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Runtime;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;

namespace AutocadArch {
 public class Bridge : IExtensionApplication {
   NamedPipeServerStream server;
   public void Initialize() {
     // Create randomised pipe name file %LOCALAPPDATA%\autocad-arch-mcp\pipe_name.txt
     // SDDL current-user-only, marshalled via Application.DocumentManager.MdiActiveDocument.Invoke
     Application.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\n[AutocadArch] Bridge loaded\n");
   }
   public void Terminate() { try{server?.Dispose();}catch{}}
 }
}
