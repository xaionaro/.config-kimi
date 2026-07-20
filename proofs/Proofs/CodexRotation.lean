import Spec.CodexRotation

namespace KimiHooks

theorem globalPrecedenceOverridesArrivalOrder :
    classifySignals [.quota, .cyber, .localHook] = .localHook := by
  rfl

theorem unknownPrefixIsSkipped :
    classifySignals [.unknown, .cyber, .quota] = .cyber := by
  rfl

theorem quotaBeforeCyberClassifiesCyber :
    classifySignals [.quota, .cyber] = .cyber := by
  rfl

theorem localBeforeQuotaRemainsLocal :
    classifySignals [.localHook, .quota] = .localHook := by
  rfl

theorem localBeforeCyberRemainsLocal :
    classifySignals [.localHook, .cyber] = .localHook := by
  rfl

theorem completeStreamIsScanned (signals : List RotationFailure) :
    scannedLineCount signals = signals.length := by
  rfl

theorem retainedTailLinesBounded (lineCount : Nat) :
    retainedTailLines lineCount ≤ 50 := by
  exact Nat.min_le_right lineCount 50

theorem exactCyberBoundaryIsRetained :
    keepCyberStreak 600 = true := by
  decide

theorem expiredCyberEntryIsPruned :
    keepCyberStreak 601 = false := by
  decide

theorem futureCooldownIsRetained :
    keepCooldown 0 1 = true := by
  decide

theorem elapsedCooldownIsPruned (nowSeconds : Int) :
    keepCooldown nowSeconds nowSeconds = false := by
  simp [keepCooldown]

theorem retriesStayPinnedAbsentWithinTaskRotation
    (pinned : String) (retryCount : Nat) :
    retryAccounts pinned (List.replicate retryCount none) =
      List.replicate retryCount pinned := by
  induction retryCount with
  | zero => rfl
  | succ count inductionHypothesis =>
      simp [List.replicate_succ, retryAccounts, accountForRetry,
        inductionHypothesis]

end KimiHooks
