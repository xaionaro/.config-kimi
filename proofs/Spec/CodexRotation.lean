namespace KimiHooks

inductive RotationFailure where
  | unknown
  | quota
  | cyber
  | localHook
  deriving BEq, DecidableEq, Repr

def higherPriorityFailure : RotationFailure → RotationFailure → RotationFailure
  | .localHook, _ => .localHook
  | _, .localHook => .localHook
  | .cyber, _ => .cyber
  | _, .cyber => .cyber
  | .quota, _ => .quota
  | _, .quota => .quota
  | _, _ => .unknown

def classifySignals (signals : List RotationFailure) : RotationFailure :=
  signals.foldl higherPriorityFailure .unknown

def scannedLineCount (signals : List RotationFailure) : Nat :=
  signals.length

def retainedTailLines (lineCount : Nat) : Nat :=
  min lineCount 50

def keepCyberStreak (ageSeconds : Int) : Bool :=
  ageSeconds ≤ 600

def keepCooldown (nowSeconds untilSeconds : Int) : Bool :=
  nowSeconds < untilSeconds

def accountForRetry (pinned : String) : Option String → String
  | none => pinned
  | some rotated => rotated

def retryAccounts (pinned : String) : List (Option String) → List String
  | [] => []
  | rotation :: rest =>
      let nextPinned := accountForRetry pinned rotation
      nextPinned :: retryAccounts nextPinned rest

end KimiHooks
