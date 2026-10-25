import { Notice } from "../../components/ui";
import type { CodeDispatch } from "../../types";

/** Confirms where a code went; in simulated-delivery demos it also shows the code. */
export function SimulatedCodeNotice({ dispatch }: { dispatch: CodeDispatch }) {
  const where = dispatch.channel === "email" ? "emailed" : "texted";
  return (
    <Notice tone={dispatch.simulated_code ? "warning" : "info"}>
      <p>
        We {where} a code to <span className="font-medium">{dispatch.destination}</span>.
        It expires in {Math.round(dispatch.expires_in_seconds / 60)} minutes.
      </p>
      {dispatch.simulated_code && (
        <p className="mt-1">
          Demo mode: no real {dispatch.channel === "email" ? "email" : "text message"} is
          sent. Your code is{" "}
          <span className="font-mono font-semibold tracking-widest">
            {dispatch.simulated_code}
          </span>
          .
        </p>
      )}
    </Notice>
  );
}
