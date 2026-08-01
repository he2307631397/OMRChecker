from pathlib import Path

p = Path('docs/weak-mark-detection.md')
text = p.read_text(encoding='utf-8')
append = r'''

## 56-sheet Current-parameter Review

Command:

```bash
python main.py -i inputs -o outputs_inputs_56_current_params
```

Result CSV:

```text
outputs_inputs_56_current_params/Results/Results_03PM.csv
```

Summary:

```text
rows 56
id_blank_cells 1
q_blank_cells 0
blank_cells 1
blank_rows 1
MX-M3658N_20260731_160125_005.png id8
```

Fallback trigger summary from `recognize_56_current_params.log`:

```text
Weak multi full-select fallback: 2
Weak mark fallback: 0
Weak multi-mark fallback: 0
```

The two full-select fallback events are the expected multi-select all-filled recoveries:

```text
Weak multi full-select fallback: field 'q10'
Weak multi full-select fallback: field 'q11'
```

The only remaining blank cell is an identifier digit, not an answer question. For `MX-M3658N_20260731_160125_005.png id8`, the configured ROI statistics were:

```text
id8 means: 0:221.51, 1:222.30, 2:223.16, 3:220.67, 4:221.69, 5:217.08, 6:191.56, 7:218.32, 8:218.43, 9:218.61
darkest candidate: 6
second-darkest gap: 25.52
```

This suggests the last identifier digit may be a weak mark around `6`, but identifier fallback is not currently enabled. The current weak single-choice fallback is intentionally limited to `QTYPE_MCQ4` answer fields, so identifier recovery should be handled as a separate, stricter feature if needed. A safe follow-up would be a dedicated `weak_identifier_params` block with stronger guards, audit logging, and validation against the full 56-sheet set.
'''
p.write_text(text + append, encoding='utf-8')
