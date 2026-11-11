import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { findingKeys } from "../findings/keys.js";
import { helpKeys } from "../help/keys.js";
import { mentionKeys } from "../mentions/keys.js";
import { useForgetClaimsWhile } from "./forgetClaims.js";

function seeded(): QueryClient {
  const client = new QueryClient();
  client.setQueryData(findingKeys.list("-1.86,51.42,-1.84,51.44", ""), { items: [{ title: "Ring ditch" }] });
  client.setQueryData(findingKeys.box("-1.86,51.42,-1.84,51.44", "", 0), { features: [] });
  client.setQueryData(findingKeys.detail("f-ring"), { title: "Ring ditch" });
  client.setQueryData(helpKeys.groups, { groups: [] });
  client.setQueryData(mentionKeys.recent, { items: [{ finding: { public_id: "f-ring", title: "Ring ditch" } }] });
  client.setQueryData(["meta"], { kept: true });
  return client;
}

function render(client: QueryClient, active: boolean) {
  return renderHook(({ on }: { on: boolean }) => useForgetClaimsWhile(on), {
    initialProps: { on: active },
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
}

describe("useForgetClaimsWhile", () => {
  it("drops every finding, help wanted and recent mentions query when the queue opens, and nothing else", () => {
    const client = seeded();
    const { rerender } = render(client, false);
    expect(client.getQueryCache().findAll({ queryKey: findingKeys.all })).toHaveLength(3);

    rerender({ on: true });
    expect(client.getQueryCache().findAll({ queryKey: findingKeys.all })).toHaveLength(0);
    expect(client.getQueryCache().findAll({ queryKey: helpKeys.all })).toHaveLength(0);
    expect(client.getQueryData(mentionKeys.recent)).toBeUndefined();
    expect(client.getQueryData(["meta"])).toEqual({ kept: true });
  });
});
