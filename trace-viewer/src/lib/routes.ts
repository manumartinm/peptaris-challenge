import { isTabId, type TabId } from "../types/tabs";

const JOB_ID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type AppRoute =
  | { kind: "home" }
  | { kind: "job"; jobId: string; tab: TabId }
  | { kind: "request"; requestId: string; tab: TabId };

export function isJobId(value: string): boolean {
  return JOB_ID.test(value);
}

function tabFromSearch(search: string): TabId {
  const tab = new URLSearchParams(search).get("tab");
  return isTabId(tab) ? tab : "home";
}

function withTab(path: string, tab: TabId): string {
  if (tab === "home") return path;
  return `${path}?tab=${tab}`;
}

export function serializeRoute(route: AppRoute): string {
  if (route.kind === "home") return "/";
  if (route.kind === "job") return withTab(`/jobs/${route.jobId}`, route.tab);
  return withTab(`/requests/${encodeURIComponent(route.requestId)}`, route.tab);
}

export function jobHref(jobId: string, tab: TabId = "home"): string {
  return serializeRoute({ kind: "job", jobId, tab });
}

export function requestHref(requestId: string, tab: TabId = "home"): string {
  return serializeRoute({ kind: "request", requestId, tab });
}

export function parseRoute(location: Pick<Location, "pathname" | "search">): AppRoute {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  const tab = tabFromSearch(location.search);
  const jobs = path.match(/^\/jobs\/([^/]+)$/);
  if (jobs && isJobId(jobs[1])) return { kind: "job", jobId: jobs[1], tab };
  const requests = path.match(/^\/requests\/([^/]+)$/);
  if (requests) {
    return {
      kind: "request",
      requestId: decodeURIComponent(requests[1]),
      tab,
    };
  }
  return { kind: "home" };
}
