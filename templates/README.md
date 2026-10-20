# Controller templates

`thanos-amc-aasd15a.shmotioncontroller` is a minimal SimHub THANOS AMC export. It keeps only:

| Field | Value | Why |
|---|---|---|
| `Output.TypeName` | `ThanosAMCControllerOutput` | tells SimHub which controller this is |
| `Output.Settings.SerialPort` | replaced by the tool (`COM69`, …) | the COM port in SimHub's Wine prefix |
| `Output.ImportType`, `Comments`, `CustomName`, `ShowOriginalName`, `AutomaticOrigin` | SimHub's neutral values | export format |
| `Output.ReviewManager` | review "Controller_Connection, Controller_Mapping" | asks you to review the connection and the actuator mapping after import |

Everything specific to one rig has been removed: actuator order and roles, spike filter values, park and unpark timings, power-check and standby options, logging flags, and the output id. After importing, set these in SimHub for your rig. Missing fields are expected to take SimHub's defaults (Inferred, not yet confirmed on a real import).

The file keeps SimHub's Windows line endings (CRLF). `.gitattributes` stores it unchanged.

**Your own export instead:** `python3 simhub_thanos.py apply --template FILE` uses any SimHub controller export and changes only its `"SerialPort"`.

**More controllers later:** add a template here and a profile entry in `PROFILES` in `simhub_thanos.py`, with the USB vendor id to look for, the template and the output file name. Only the THANOS AMC has been tested.
