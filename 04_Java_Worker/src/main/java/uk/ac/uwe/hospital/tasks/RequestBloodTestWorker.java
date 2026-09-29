package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;

import java.time.Instant;
import java.util.Map;

/**
 * {@code request-blood-test} - orders the pre-cycle blood test the chemotherapy
 * pathway depends on.
 *
 * <p>The clinical decision that follows it (fit to continue, delay, or change the
 * plan) is deliberately <b>not</b> taken here. The case study is explicit that
 * these are clinical decisions which administrative staff and systems must not
 * make, so this worker only requests the test and records when the result is due.
 * {@code fitToContinue} is left to the Consultant's review task.
 *
 * <p>中文：本类服务于 BPMN 中"申请血液检查"的 Zeebe 服务任务，作业类型为
 * {@code request-blood-test}。它在化疗路径上只完成一件事：向检验系统下单并登记结果到期时间。
 * "是否适合继续、是否延期、是否改方案"属于临床决策，按案例研究的规定行政人员与系统都不得代做，
 * 所以工人只下单并记录到期时间，绝不写入 {@code fitToContinue}，该变量只由顾问医师的复核任务填写。
 */
public class RequestBloodTestWorker extends AbstractWorker {

    /** 中文：BPMN 服务任务绑定的作业类型，必须与模型中 zeebe:taskDefinition 的 type 完全一致。 */
    public static final String JOB_TYPE = "request-blood-test";

    public RequestBloodTestWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"申请血液检查"作业。读取患者与化疗周期信息，向模拟检验服务下单，
     * 并把申请凭证、周期和结果到期日写回流程变量，供后续等待与顾问医师复核使用。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：patientId 为必填输入；cycleReference 默认"next cycle"，episodeId 缺失时按患者编号推导。
        String patientId = ctx.requireString("patientId");
        String cycle = ctx.findString("cycleReference").orElse("next cycle");
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));

        // 中文：外部检验系统为模拟实现，返回凭证与结果到期日；真正的化验结果不在这里产生。
        ExternalServices.Laboratory.Result result =
                ExternalServices.Laboratory.requestBloodTest(patientId, cycle);

        // 中文：写回 bloodTestRequested、凭证、所属周期和到期日，流程据此设置定时等待，
        // 到期后转入顾问医师复核；注意这里刻意不写 fitToContinue，避免系统越权做临床判断。
        ctx.set("episodeId", episodeId)
           .set("bloodTestRequested", true)
           .set("bloodTestReference", result.reference())
           .set("bloodTestForCycle", cycle)
           .set("bloodTestDueDate", result.dueDate().toString())
           .set("bloodTestRequestedAt", Instant.now().toString())
           .note("ordered " + result.reference() + " for " + cycle + ", due " + result.dueDate());

        // 中文：把申请记录挂到本次就诊的 laboratory 分类下，供审计与退款/报表流程回溯，
        // 记录内容只含凭证、周期与到期日，不含患者临床细节，属于数据最小化处理。
        HospitalStore.get().put(episodeId, "laboratory", result.reference(), Map.of(
                "reference", result.reference(),
                "cycle", cycle,
                "dueDate", result.dueDate().toString()));
    }
}
