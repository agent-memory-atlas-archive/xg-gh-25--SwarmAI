## 需求溯源审计 (Requirement Provenance Audit)

### 原始意图 (Original Intent)
> Action 3a (#8 bare-artifact uniqueness): a bare (run_id-less) artifact filename is {type}-{date}[-topic].json, so a second same-day same-type same-topic publish OVERWRITES the first file while the manifest appends a new id -> two ids read the same data. Fix: append the artifact_id to the bare filename ({type}-{date}[-topic]-{art_id}.json) matching the run-scoped scheme, so a second publish cannot overwrite. 461 live bare files + 3 standalone skills depend on bare; this is a uniqueness fix only.

### 需求推导 (Derivation)
## Requirements

| ID | work_class | source | status | AC present | Acceptance (GWT) |
|----|-----------|--------|--------|:---------:|------------------|
| FR-1 | bug | user-stated: Kiro #8 — bare overwrite + id aliasing (reproduced) | confirmed | ● | Given two bare publishes of the same type/date/topic, when both land, then two distinct files on disk; the first id's data is preserved |

### 澄清问答 (Clarifications — who decided what)
_(无澄清记录 / no clarifications)_

### ⚠️ 遗留 / 未闭合 (Leftover — what the AI decided for you)
✅ 无未闭合问题 (no leftover — all requirements closed, no AI assumptions)