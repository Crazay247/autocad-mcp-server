using System.Security.AccessControl;
using System.Security.Principal;

namespace AutocadArch {
 /// <summary>Stub security — SDDL current-user-only for NamedPipeServerStream.</summary>
 public static class Security {
   public static PipeSecurity CreateCurrentUserOnlySecurity() {
     var sid = WindowsIdentity.GetCurrent()?.User;
     var ps = new PipeSecurity();
     if (sid != null) {
       ps.AddAccessRule(new PipeAccessRule(sid, PipeAccessRights.FullControl, AccessControlType.Allow));
     }
     return ps;
   }
 }
}
