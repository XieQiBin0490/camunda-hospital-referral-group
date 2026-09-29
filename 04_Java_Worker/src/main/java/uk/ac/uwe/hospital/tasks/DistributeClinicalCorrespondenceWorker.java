package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;

import java.time.Instant;
import java.util.Map;

/**
 * {@code distribute-clinical-correspondence} - dispatches clinical letters
 * through the approved communication channels.
 *
 * <p>The case study separates clinical content from administrative handling: the
 * Consultant approves the letter, administrative staff check and distribute it,
 * and a suspected clinical error goes back to the Consultant. This worker is the
 * distribution half only. It refuses to dispatch a letter that has not been
 * approved, which is how the "administrative staff must not change clinical
 * meaning" rule is enforced in code rather than by convention.
 *
 * <p>中文：本类服务于 BPMN 中"分发临床信函"的 Zeebe 服务任务，作业类型为
 * {@code distribute-clinical-correspondence}。业务流程上它对应职能分工里的"分发"一半：
 * 顾问医师已完成信函内容的审核，行政人员这里只负责投递，不修改也不重新解释临床含义。
 * 因此，只要信函尚未获批或已发现疑似临床错误，本工人都拒绝发送，并把阻止原因写入流程变量，
 * 由后续网关分支和人工处理接手。
 */
public class DistributeClinicalCorrespondenceWorker extends AbstractWorker {

    /** 中文：BPMN 服务任务绑定的作业类型，必须与模型中 zeebe:taskDefinition 的 type 完全一致。 */
    public static final String JOB_TYPE = "distribute-clinical-correspondence";

    public DistributeClinicalCorrespondenceWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"分发临床信函"作业。读取信函是否获批、是否疑似临床错误等输入变量，
     * 在允许发送时调用外部渠道投递并回写投递结果；被拒绝的分支只记录阻止原因，不产生投递动作。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：patientId 是必填输入，缺失时 requireString 会直接让本次作业失败重试。
        String patientId = ctx.requireString("patientId");
        // 中文：以下三个布尔量来自流程变量；读取时给出默认值，保证人工表单没填字段时也不会抛异常。
        boolean approved = ctx.bool("letterApproved", false);
        boolean suspectedError = ctx.bool("suspectedClinicalError", false);
        // 中文：投递渠道由无障碍格式需求决定，默认走普通邮寄，这是可访问性要求的落地方式。
        String channel = ctx.bool("accessibleFormatRequired", false) ? "accessible format" : "post";
        // 中文：收件人默认发给患者本人；episodeId 缺失时按患者编号推导，保证留痕总能落到某次就诊上。
        String recipients = ctx.findString("letterRecipients").orElse("patient");
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));

        // A suspected clinical error and an unapproved letter are both "do not send",
        // but they are different facts and are reported differently.
        if (suspectedError || !approved) {
            // 中文：不发送时写回 correspondenceSent=false，并把两种原因区分开：
            // 疑似临床错误要退回顾问医师，未获批则等待审核，下游网关与人工任务据此分流。
            ctx.set("episodeId", episodeId)
               .set("correspondenceSent", false)
               .set("correspondenceBlockedReason", suspectedError
                       ? "suspected clinical error returned to the Consultant"
                       : "letter not yet approved by the Consultant")
               .set("correspondenceCheckedAt", Instant.now().toString())
               .note("dispatch withheld: " + (suspectedError ? "suspected clinical error" : "not approved"));
            return;
        }

        // 中文：通过审批检查后才调用外部通信服务；这里的渠道与已记录的收件人被原样透传，
        // 保证投递结果与审批时的意图一致。外部投递失败会抛异常，由引擎按重试策略处理。
        String reference = ExternalServices.Correspondence.dispatch(channel, recipients);

        // 中文：投递成功写回 correspondenceSent=true 及凭证、渠道、收件人和时间戳，
        // 这些变量供流程网关判断是否进入"等待患者回复/结束"分支，也是审计所需的证据链。
        ctx.set("episodeId", episodeId)
           .set("correspondenceSent", true)
           .set("correspondenceReference", reference)
           .set("correspondenceChannel", channel)
           .set("correspondenceRecipients", recipients)
           .set("correspondenceSentAt", Instant.now().toString())
           .note("dispatched " + reference + " to " + recipients + " by " + channel);

        // 中文：仅落库投递所需的引用信息（凭证、渠道、收件人、时间），不写入信函正文等临床内容，
        // 符合数据最小化要求；这些记录同时也是管理报表统计信件数量的事实来源。
        HospitalStore.get().put(episodeId, "correspondence", reference, Map.of(
                "reference", reference,
                "channel", channel,
                "recipients", recipients,
                "sentAt", Instant.now().toString()));
    }
}
