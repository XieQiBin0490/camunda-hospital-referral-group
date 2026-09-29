/**
 * Start one referring-organisation instance with the variables its worker needs.
 *
 *   node 09_Tests_and_Tools/start-referring.mjs [patientId] [organisation]
 *
 * PR_ReferringOrganisation starts with a plain (none) start event, so it is
 * started explicitly rather than by a message. Its first activity is the service
 * task RO_ComposeReferral, and SubmitPatientReferralWorker requires `patientId`
 * as a hard input - the models declare no error boundary event, so starting this
 * process with an empty variable set turns the thrown INVALID_JOB_INPUT into an
 * unhandled-error incident. That is exactly what happened the first time, which
 * is why this script exists: it supplies the variables the worker demands.
 *
 * The rest of the round trip needs no input:
 *   RO_SendReferral  publishes `Patient referral`      -> starts PR_Operational_Merged
 *   the hospital     publishes `Referral outcome...`   -> completes RO_AwaitOutcome
 */

const BASE = process.env.C8_BASE || 'http://127.0.0.1:8080/v2';
const AUTH = 'Basic ' + Buffer.from(process.env.C8_USER ? `${process.env.C8_USER}:${process.env.C8_PASSWORD || ''}` : 'demo:demo').toString('base64');

const patientId = process.argv[2] || 'P-1002';
const referringOrganisation = process.argv[3] || 'Northside GP Practice';

const body = {
  processDefinitionId: 'PR_ReferringOrganisation',
  variables: { patientId, referringOrganisation },
};

console.log(`POST ${BASE}/process-instances`);
console.log(`  processDefinitionId : PR_ReferringOrganisation`);
console.log(`  patientId           : ${patientId}`);
console.log(`  referringOrganisation: ${referringOrganisation}`);
console.log('');

const res = await fetch(`${BASE}/process-instances`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: AUTH },
  body: JSON.stringify(body),
});

const text = await res.text();
console.log(`HTTP ${res.status}`);
console.log(text);
console.log('');

if (!res.ok) {
  console.log('The instance was NOT created. Common causes:');
  console.log('  * the Camunda 8 cluster is not running on 127.0.0.1:8080');
  console.log('  * PR_ReferringOrganisation is not deployed - run deploy-all.mjs first');
  process.exit(1);
}

console.log('Instance created. Now watch the worker window for:');
console.log("  SubmitPatientReferralWorker  ... -> completed  [composed referral REFRL-...]");
console.log("  PublishPatientReferralWorker published message 'Patient referral' key=...");
