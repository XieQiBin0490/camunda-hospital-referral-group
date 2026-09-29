# Test evidence

Evidence for the acceptance test run recorded in Task 04 of the portfolio.

| File | Contents |
| --- | --- |
| `acceptance-run.json` | One record per executed test case: process instance key, final state, every element instance reached, the variables set at each step, the incidents raised and the full completion trace |
| `acceptance-run.log` | The console log of the same run, with a plain-language line per case |
| `../../05_Test_Evidence/cluster.txt` | The cluster, the deployed process definitions and the deployed forms |
| `../../05_Test_Evidence/validation.txt` | Schema, lint, structural and layout validation of the delivered models |

The run is reproducible while the cluster is available:

```
node 09_Tests_and_Tools/deploy-all.mjs      # deploy the 68 forms and the 4 models
node 09_Tests_and_Tools/run-acceptance.mjs  # execute the acceptance cases
```
