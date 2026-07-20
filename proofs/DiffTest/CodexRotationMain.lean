import Proofs.CodexRotation

open KimiHooks

def parseSignal : String → Option RotationFailure
  | "unknown" => some .unknown
  | "quota" => some .quota
  | "cyber" => some .cyber
  | "local_hook_deny" => some .localHook
  | _ => none

def renderFailure : RotationFailure → String
  | .unknown => "unknown"
  | .quota => "quota"
  | .cyber => "cyber"
  | .localHook => "local_hook_deny"

def main (args : List String) : IO UInt32 := do
  let signals := args.filterMap parseSignal
  IO.println (renderFailure (classifySignals signals))
  IO.println (retainedTailLines (scannedLineCount signals))
  return 0
