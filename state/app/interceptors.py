import grpc


class AllowListInterceptor(grpc.aio.ServerInterceptor):
    def __init__(self, allow_list):
        self.allow_list = allow_list

    async def intercept_service(self, continuation, handler_call_details):
        method = handler_call_details.method

        # Example placeholder:
        # Extract caller identity from metadata
        metadata = dict(handler_call_details.invocation_metadata)

        caller = metadata.get("caller-id")

        if caller not in self.allow_list:
            return grpc.unary_unary_rpc_method_handler(
                self._unauthorized
            )

        return await continuation(handler_call_details)

    async def _unauthorized(self, request, context):
        await context.abort(
            grpc.StatusCode.PERMISSION_DENIED,
            "Caller not allowed",
        )