package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.BpmnErrorException;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;
import uk.ac.uwe.hospital.support.MessagePublisher;

import java.time.Instant;
import java.util.Map;

/**
 * {@code send-referral-outcome} - tells the referring organisation what was
 * decided about the referral.
 *
 * <p>This is the one automated activity whose failure the process must not hide:
 * REQ-07 requires the outcome to be notified, so a missing decision is treated as
 * a defect rather than defaulted away. The decision is read, never invented.
 *
 * <p>中文：本类服务于 BPMN 发送任务 T_NotifyReferralOutcome（把转诊结论通知转诊机构），
 * 作业类型为 {@code send-referral-outcome}。它接在网关 G_ReferralDecision 之后，承接
 * referralDecision = "rejected" 这条默认分支，负责把顾问医师已经作出的决定送达转诊机构。
 * 这里的核心业务约束是 REQ-07：结论通知必须真的发出，所以本工人只读取决定、绝不臆造决定；
 * 决定缺失时按数据缺陷处理（抛出具名 BPMN 错误），而不是默认成某个结论蒙混过关。
 */
public class SendReferralOutcomeWorker extends AbstractWorker {

    /** 中文：作业类型标识，必须与模型中 zeebe:taskDefinition 的 type 逐字一致，否则引擎不会派发作业。 */
    public static final String JOB_TYPE = "send-referral-outcome";

    /** 中文：用"工人族名 + 作业类型"拼出订阅名，便于在 Zeebe 与日志中区分同一类型的多个工人实例。 */
    public SendReferralOutcomeWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    /** 中文：返回本工人订阅的作业类型，基类据此注册 Zeebe 作业工人并接收该类型的作业。 */
    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"通知转诊结论"作业。读取顾问医师已经登记的决定，通过外部通信服务把结论信函
     * 送达转诊机构并写回通知凭证；决定缺失属于数据缺陷，直接抛出具名 BPMN 错误而不做任何默认。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：patientId 是必填输入，缺失会让本次作业以校验错误结束，提示上游表单数据不完整。
        String patientId = ctx.requireString("patientId");
        // 中文：referralDecision 既是网关 G_ReferralDecision 的分流依据，也是信函要告知的结论，
        // 中文：因此它缺失时无从猜测：抛出具名 BPMN 错误 REFERRAL_DECISION_MISSING，
        // 中文：交给边界事件或人工环节接手，避免给转诊机构寄出一封结论不明的通知。
        String decision = ctx.findString("referralDecision")
                .orElseThrow(() -> new BpmnErrorException("REFERRAL_DECISION_MISSING",
                        "no referralDecision is set, so no outcome can be notified"));
        // 中文：收件机构缺失时退化为中性描述，保证信函抬头与审计记录不会为空。
        String organisation = ctx.findString("referringOrganisation").orElse("referring organisation");
        // 中文：episodeId 缺失时按患者号推导，使通知这种跨组织动作也能归到同一次就诊的档案下。
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));

        // 中文：外部通信服务不可用会抛可重试异常，由引擎重试。注意这里不能在失败时就写
        // 中文：outcomeNotified = true：REQ-07 要求通知确实送达，谎报成功比失败更糟。
        String reference = ExternalServices.Correspondence.dispatch("letter", organisation);

        // 中文：写回通知结果：outcomeNotified 表明结论已送达，outcomeNotifiedDecision 保存所通知的
        // 中文：决定本身，便于事后核对"通知内容与顾问决定一致"；凭证与时间构成 REQ-07 的追溯证据。
        ctx.set("episodeId", episodeId)
           .set("outcomeNotified", true)
           .set("outcomeNotifiedDecision", decision)
           .set("outcomeLetterReference", reference)
           .set("outcomeNotifiedTo", organisation)
           .set("outcomeNotifiedAt", Instant.now().toString())
           .note("notified " + organisation + " that the referral was " + decision);

        // 中文：按 episodeId 归集结论通知记录（集合名 outcomes，键为凭证号），
        // 中文：与流程变量互为印证，供 REQ-07 的追溯查询使用。
        HospitalStore.get().put(episodeId, "outcomes", reference, Map.of(
                "reference", reference,
                "decision", decision,
                "organisation", organisation,
                "notifiedAt", Instant.now().toString()));

        // 中文：跨池回传。这是整条链路的第二跳：把结论作为消息发回转诊机构所在的池，
        // 中文：由对方等待中的消息捕获事件接收。关联键必须与转诊池上的表达式一致，
        // 中文：因此同样取 referralReference，缺失时才退回关联句柄。
        // 中文：这一跳是"通知对方"，不是本活动的交付物——结论信函已经发出，
        // 所以消息发不出去只记为受阻，不会让本作业失败，也不会推翻 outcomeNotified。
        String referralReference = ctx.findString("referralReference").orElse(episodeId);
        long outcomeMessageKey = MessagePublisher.publish(
                "Referral outcome notification", referralReference, episodeId, Map.of(
                        "referralReference", referralReference,
                        "referralDecision", decision,
                        "episodeId", episodeId,
                        "outcomeLetterReference", reference,
                        "outcomeNotifiedTo", organisation));
        // 中文：写回回传结果。消息键为负表示未发出，该事实必须落盘，
        // 中文：否则"结论已通知转诊机构"会显得比实际更完整。
        ctx.set("outcomeMessageKey", outcomeMessageKey)
           .note(outcomeMessageKey >= 0
                   ? "published 'Referral outcome notification' key=" + outcomeMessageKey
                   : "could not publish 'Referral outcome notification' for " + referralReference);
    }
}
