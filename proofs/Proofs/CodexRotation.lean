import Spec.CodexRotation

namespace KimiHooks

theorem firstQuotaIsDecisive :
    classifySignals [.quota, .cyber, .localHook] = .quota := by
  rfl

theorem unknownPrefixIsSkipped :
    classifySignals [.unknown, .cyber, .quota] = .cyber := by
  rfl

theorem decisiveScanStopsAfterOne (decisive : RotationFailure)
    (decisive_ne_unknown : decisive ≠ .unknown) (rest : List RotationFailure) :
    scannedLineCount (decisive :: rest) = 1 := by
  cases decisive <;> simp_all [scannedLineCount]

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

end KimiHooks
