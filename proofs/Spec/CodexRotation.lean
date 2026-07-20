namespace KimiHooks

inductive RotationFailure where
  | unknown
  | quota
  | cyber
  | localHook
  deriving BEq, DecidableEq, Repr

def classifySignals : List RotationFailure → RotationFailure
  | [] => .unknown
  | .unknown :: rest => classifySignals rest
  | decisive :: _ => decisive

def scannedLineCount : List RotationFailure → Nat
  | [] => 0
  | .unknown :: rest => scannedLineCount rest + 1
  | _ :: _ => 1

def retainedTailLines (lineCount : Nat) : Nat :=
  min lineCount 50

def keepCyberStreak (ageSeconds : Int) : Bool :=
  ageSeconds ≤ 600

def keepCooldown (nowSeconds untilSeconds : Int) : Bool :=
  nowSeconds < untilSeconds

end KimiHooks
