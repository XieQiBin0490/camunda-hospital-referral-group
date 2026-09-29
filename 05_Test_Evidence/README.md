# Build 1.0 evidence

Evidence for the HPAS initial release, build 1.0, as deployed and executed on
Camunda 8 Run 8.10.0-alpha5.

| File or folder | Contents |
| --- | --- |
| `cluster.txt` | The runtime, the six deployed process definitions, the 68 deployed forms and the execution summary |
| `validation.txt` | Schema round-trip, Camunda compatibility lint, structural audit and layout audit for the four delivered models |
| `acceptance-run.json` | One record per executed case: process instance key, final state, every element instance reached, variables set at each step, incidents and the full completion trace |
| `acceptance-run.log` | The console log of the same run |
| `screenshots/` | Operate and Tasklist screenshots of the running cluster |

## Result

- 7 of 7 process definitions deployed
- 68 of 68 Camunda Forms deployed
- 18 of 18 acceptance test cases passed
- 0 incidents during the acceptance run
- 4 defects found by deploying and executing (`DEP-01` to `DEP-04`), all fixed at source and re-verified

## Reproducing the run

```
node 09_Tests_and_Tools/build.mjs          # regenerate the .bpmn models
node 09_Tests_and_Tools/build-forms.mjs    # regenerate the Camunda Forms
node 09_Tests_and_Tools/deploy-all.mjs     # deploy forms and models to the running cluster
node 09_Tests_and_Tools/run-acceptance.mjs # execute the acceptance cases
```
