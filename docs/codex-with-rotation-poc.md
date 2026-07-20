# Codex credential-pool immutability PoC

Date: `2026-07-20T09:10:34Z` (UTC). [T1: captured command output]

Runtime: `codex-cli 0.144.6`. [T1: `codex --version`]

The probe hashed and statted all three pool files, ran the real wrapper with the
trivial prompt `say ok`, then repeated the same hash/stat manifest and compared
the two manifests with `cmp -s`. It did not print or inspect auth JSON content.
[T1: probe command and output below]

```bash
printf 'say ok\n' |
  ~/.kimi-code/bin/codex-with-rotation --label poc -- 'say ok'
```

## Recorded output

```text
utc=2026-07-20T09:10:34Z
codex-cli 0.144.6
--- before ---
653bc5f8cc2cca345071b02a5835c4106ef987b7d6b71ab5f9cf55d74fc42750  /home/pheona/.codex/auth.json
STAT /home/pheona/.codex/auth.json size=4102 mode=600 uid=1003 gid=1003 mtime=2026-07-14 07:23:19.803700699 +0000 inode=33469146
1f6f92e3bd8e1df95e6c7fd52282124937f361536563910023010aad43bfe7ef  /home/pheona/.codex/auth.json-danusya
STAT /home/pheona/.codex/auth.json-danusya size=4323 mode=664 uid=1003 gid=1003 mtime=2026-07-17 23:17:19.710965601 +0000 inode=33464754
6aa9aa275399988ab3b73a47ef21318376594b0e7e646bc9bf8851ec0e5304ee  /home/pheona/.codex/auth.json-xaionaro
STAT /home/pheona/.codex/auth.json-xaionaro size=4021 mode=600 uid=1003 gid=1003 mtime=2026-07-14 18:23:51.444031569 +0000 inode=33464741
--- wrapper ---
exit=0
stdout:
{"type":"thread.started","thread_id":"019f7eca-a2f9-7660-b919-6b40e338d6fd"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"ok"}}
{"type":"turn.completed","usage":{"input_tokens":14738,"cached_input_tokens":0,"output_tokens":35,"reasoning_output_tokens":28}}
stderr:
{"wrapper":"codex-with-rotation","class":"success","label":"poc","task_sig":"19fd345591dabee07ae09f7ce1f20e14a0cd3747e1b6bccd34db52fb2835f580","codex_exit":0,"attempts":1}
--- after ---
653bc5f8cc2cca345071b02a5835c4106ef987b7d6b71ab5f9cf55d74fc42750  /home/pheona/.codex/auth.json
STAT /home/pheona/.codex/auth.json size=4102 mode=600 uid=1003 gid=1003 mtime=2026-07-14 07:23:19.803700699 +0000 inode=33469146
1f6f92e3bd8e1df95e6c7fd52282124937f361536563910023010aad43bfe7ef  /home/pheona/.codex/auth.json-danusya
STAT /home/pheona/.codex/auth.json-danusya size=4323 mode=664 uid=1003 gid=1003 mtime=2026-07-17 23:17:19.710965601 +0000 inode=33464754
6aa9aa275399988ab3b73a47ef21318376594b0e7e646bc9bf8851ec0e5304ee  /home/pheona/.codex/auth.json-xaionaro
STAT /home/pheona/.codex/auth.json-xaionaro size=4021 mode=600 uid=1003 gid=1003 mtime=2026-07-14 18:23:51.444031569 +0000 inode=33464741
--- comparison ---
POOL_HASH_AND_STAT_UNCHANGED=yes
```

The wrapper completed in one attempt, and the before/after manifests were
identical, including SHA-256, size, mode, ownership, modification time, and
inode for all three source pool files. [T1: wrapper status and `cmp -s` result]

The probe also recorded that `auth.json-danusya` was already mode `0664`; the
wrapper preserved that pre-existing source mode and copied the active
credential into its disposable home as mode `0600`. This artifact records the
observation but does not change credential-file policy or permissions.
[T1: before/after stat output; synthetic suite auth-mode assertion]
