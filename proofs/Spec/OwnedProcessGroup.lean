namespace CodexHooks

inductive OwnedGroupEvent where
  | registerIdentity
  | sendTerm
  | sendKill
  | observeLeaderExit
  | reapLeader
  | observeGroupAbsence
  | signalUnrelated
deriving DecidableEq, Repr

inductive OwnedGroupPhase where
  | idle
  | identityReserved
  | termSent
  | killSent
  | leaderExitObserved
  | leaderReaped
  | groupAbsenceObserved
deriving DecidableEq, Repr

structure OwnedGroupState where
  phase : OwnedGroupPhase := .idle
  rejected : Bool := false
  unrelatedTouched : Bool := false
deriving DecidableEq, Repr

def OwnedGroupState.registered (state : OwnedGroupState) : Bool :=
  match state.phase with
  | .idle => false
  | .identityReserved => true
  | .termSent => true
  | .killSent => true
  | .leaderExitObserved => true
  | .leaderReaped => true
  | .groupAbsenceObserved => true

def OwnedGroupState.identityReserved (state : OwnedGroupState) : Bool :=
  match state.phase with
  | .identityReserved => true
  | .termSent => true
  | .killSent => true
  | .leaderExitObserved => true
  | .idle => false
  | .leaderReaped => false
  | .groupAbsenceObserved => false

def OwnedGroupState.termWasSent (state : OwnedGroupState) : Bool :=
  match state.phase with
  | .termSent => true
  | .killSent => true
  | .leaderExitObserved => true
  | .leaderReaped => true
  | .groupAbsenceObserved => true
  | .idle => false
  | .identityReserved => false

def OwnedGroupState.killWasSent (state : OwnedGroupState) : Bool :=
  match state.phase with
  | .killSent => true
  | .leaderExitObserved => true
  | .leaderReaped => true
  | .groupAbsenceObserved => true
  | .idle => false
  | .identityReserved => false
  | .termSent => false

def OwnedGroupState.exitWasObserved (state : OwnedGroupState) : Bool :=
  match state.phase with
  | .leaderExitObserved => true
  | .leaderReaped => true
  | .groupAbsenceObserved => true
  | .idle => false
  | .identityReserved => false
  | .termSent => false
  | .killSent => false

def OwnedGroupState.leaderWasReaped (state : OwnedGroupState) : Bool :=
  match state.phase with
  | .leaderReaped => true
  | .groupAbsenceObserved => true
  | .idle => false
  | .identityReserved => false
  | .termSent => false
  | .killSent => false
  | .leaderExitObserved => false

def OwnedGroupState.absenceWasObserved (state : OwnedGroupState) : Bool :=
  match state.phase with
  | .groupAbsenceObserved => true
  | .idle => false
  | .identityReserved => false
  | .termSent => false
  | .killSent => false
  | .leaderExitObserved => false
  | .leaderReaped => false

def OwnedGroupState.reapCount (state : OwnedGroupState) : Nat :=
  match state.phase with
  | .leaderReaped => 1
  | .groupAbsenceObserved => 1
  | .idle => 0
  | .identityReserved => 0
  | .termSent => 0
  | .killSent => 0
  | .leaderExitObserved => 0

def OwnedGroupState.reject (state : OwnedGroupState) : OwnedGroupState :=
  { state with rejected := true }

def ownedGroupStep
    (state : OwnedGroupState) (event : OwnedGroupEvent) : OwnedGroupState :=
  match state.rejected with
  | true => state
  | false =>
      match state.phase, event with
      | .idle, .registerIdentity => { state with phase := .identityReserved }
      | .identityReserved, .sendTerm => { state with phase := .termSent }
      | .termSent, .sendKill => { state with phase := .killSent }
      | .killSent, .observeLeaderExit => {
          state with phase := .leaderExitObserved
        }
      | .leaderExitObserved, .reapLeader => {
          state with phase := .leaderReaped
        }
      | .leaderReaped, .observeGroupAbsence => {
          state with phase := .groupAbsenceObserved
        }
      | _, _ => state.reject

def ownedGroupRun (events : List OwnedGroupEvent) : OwnedGroupState :=
  events.foldl ownedGroupStep {}

def linuxContainmentAdmissionAccepted
    (linux parentMatched parentDeathVerified subreaperVerified pidfdVerified
      controlCloseOnExec : Bool) : Bool :=
  linux && parentMatched && parentDeathVerified && subreaperVerified &&
    pidfdVerified && controlCloseOnExec

end CodexHooks
