using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;

namespace AutocadArch {
 /// <summary>Stub handlers — marshalled via DocumentManager.MdiActiveDocument.Invoke -> Transaction.</summary>
 public static class Handlers {
   public static object HandleDrawingCreate(Document doc, string name) {
     // TODO: Transaction -> Database creation, marshalled to doc thread
     return new { ok = true, payload = "dotnet drawing_create stub" };
   }
 }
}
