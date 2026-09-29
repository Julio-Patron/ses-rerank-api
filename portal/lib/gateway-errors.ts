export type GatewayErrorKind =
  | "configuration"
  | "authentication"
  | "network"
  | "dependency"
  | "timeout"
  | "gateway";

export class GatewayError extends Error {
  constructor(
    public readonly kind: GatewayErrorKind,
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "GatewayError";
  }
}

export function gatewayErrorMessage(error: unknown): string {
  if (!(error instanceof GatewayError)) {
    return "The Portal could not complete the Gateway request. Try again.";
  }

  switch (error.kind) {
    case "configuration":
      return "Configure a valid Gateway URL and API key in Settings.";
    case "authentication":
      return "The Gateway rejected this API key. Verify or rotate it in Settings.";
    case "network":
      return "The browser could not reach the Gateway. Check the URL, service, and CORS configuration.";
    case "dependency":
      return "The Gateway is reachable, but a required service is unavailable. Check readiness and retry.";
    case "timeout":
      return "The Gateway did not respond before the request timeout. Check service health and retry.";
    case "gateway":
      return error.message || "The Gateway returned an unexpected error.";
  }
}
