package uk.ac.uwe.hospital.support;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

/**
 * Puts HTTP basic credentials on every gRPC call the worker fleet makes.
 *
 * <p>Once the cluster is configured with {@code camunda.security.authorizations.enabled}
 * and {@code unprotected-api: false}, the gateway stops serving anonymous callers:
 * activation requests do not fail loudly, they simply return nothing, so the fleet looks
 * healthy while every process parks on its first service task. This interceptor is what
 * makes the two settings usable together.
 *
 * <p>It is only installed when a username is configured, so a developer running the
 * shipped c8run defaults without authorization keeps working unchanged.
 *
 * <p>中文：本类为工作器的每一次 gRPC 调用附加 HTTP Basic 凭据。集群一旦开启授权并关闭
 * 未受保护接口，网关就不再服务匿名调用方；此时作业激活不会显式报错，而只是返回空结果，
 * 于是工作器看起来运行正常，而所有流程都停在第一个服务任务上。这个拦截器让两项设置可以同时
 * 启用。只有在配置了用户名时才会安装，因此沿用 c8run 默认配置（不开启授权）的开发者不受影响。
 */
public final class BasicAuthInterceptor implements ClientInterceptor {

    /** 中文：gRPC 元数据里的 Authorization 键，值与 HTTP 头完全一致。 */
    private static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

    /** 中文：预先算好的 Basic 头，避免每次调用都重新拼接与编码。 */
    private final String header;

    /** 中文：用用户名与口令构造；口令本身不落日志，只保留编码后的头部。 */
    public BasicAuthInterceptor(String username, String password) {
        this.header = "Basic " + Base64.getEncoder().encodeToString(
                (username + ":" + password).getBytes(StandardCharsets.UTF_8));
    }

    /** 中文：包装每一次调用，在真正发出前把头写入元数据。 */
    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method, CallOptions options, Channel next) {
        return new ForwardingClientCall.SimpleForwardingClientCall<>(next.newCall(method, options)) {
            @Override
            public void start(Listener<RespT> responseListener, Metadata headers) {
                headers.put(AUTHORIZATION, header);
                super.start(responseListener, headers);
            }
        };
    }
}
