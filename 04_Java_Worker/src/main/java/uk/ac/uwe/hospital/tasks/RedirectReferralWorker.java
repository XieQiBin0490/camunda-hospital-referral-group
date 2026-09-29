package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;

import java.time.Instant;
import java.util.Map;

/**
 * {@code redirect-referral} - sends a referral the hospital will not accept to
 * another specialist service.
 *
 * <p>The destination must have been chosen by the Consultant, so an empty
 * destination is reported as an input defect rather than guessed at. The
 * redirect reference is recorded because REQ-07 requires the decision to be
 * traceable.
 *
 * <p>中文：本类服务于 BPMN 发送任务 T_RedirectReferral（把转诊改派到其他专科服务），
 * 作业类型为 {@code redirect-referral}。它位于网关 G_ReferralDecision 的
 * referralDecision = "redirected" 分支上：当本院不接收该转诊、但患者仍应得到诊治时，
 * 由顾问医师选定去向，本工人负责发出改派并记录改派凭证，使"未被接收"这一决定同样可追溯（REQ-07）。
 * 目的地必须来自临床人员的判断，因此缺失时按输入缺陷报错，而不是替顾问随便挑一个专科。
 */
public class RedirectReferralWorker extends AbstractWorker {

    /** 中文：作业类型标识，必须与模型中 zeebe:taskDefinition 的 type 逐字一致，否则引擎不会派发作业。 */
    public static final String JOB_TYPE = "redirect-referral";

    /** 中文：用"工人族名 + 作业类型"拼出订阅名，便于在 Zeebe 与日志中区分同一类型的多个工人实例。 */
    public RedirectReferralWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    /** 中文：返回本工人订阅的作业类型，基类据此注册 Zeebe 作业工人并接收该类型的作业。 */
    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"改派转诊"作业。读取顾问医师选定的去向，调用外部通信服务发出改派，
     * 并写回改派凭证，使"本院不接收、转往他处"这一决定同样留痕可查（REQ-07）。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：patientId 是必填输入，缺失即视为上游数据缺陷，以校验异常终止本次作业。
        String patientId = ctx.requireString("patientId");
        // 中文：redirectDestination 必须由顾问医师选定，本工人不做任何默认或猜测：
        // 中文：填错去向等于把患者送错专科，属于临床安全问题，所以缺失时直接报输入缺陷。
        String destination = ctx.requireString("redirectDestination");
        // 中文：episodeId 缺失时按患者号推导，保证改派记录仍归集在同一次就诊之下。
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));

        // 中文：调用外部通信服务发出改派，返回的凭证号用于后续追踪与对账；
        // 中文：服务不可用时抛可重试异常，由引擎重试，不会在此写回"已改派"。
        String reference = ExternalServices.Correspondence.redirect(destination);

        // 中文：写回改派结果：redirectSent 标记动作完成，redirectReference 与 redirectedToService
        // 中文：分别保存凭证和实际去向，redirectedAt 记录时间，共同支撑 REQ-07 的可追溯性要求。
        ctx.set("episodeId", episodeId)
           .set("redirectSent", true)
           .set("redirectReference", reference)
           .set("redirectedToService", destination)
           .set("redirectedAt", Instant.now().toString())
           .note("redirected to " + destination + " as " + reference);

        // 中文：按 episodeId 归集改派记录（集合名 redirects，键为凭证号），
        // 中文：便于事后统计改派去向，并核对每一例未被接收的转诊都得到了处理。
        HospitalStore.get().put(episodeId, "redirects", reference, Map.of(
                "reference", reference,
                "destination", destination,
                "redirectedAt", Instant.now().toString()));
    }
}
