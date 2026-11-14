import { type ComponentType, createContext } from "react";

/**
 * What an error state offers after its own action, given by the app: the
 * shell provides "Report a problem" (`features/problem`). Outside it, as in
 * the component gallery and the tests of `ui/` alone, nothing is offered.
 */
export const ErrorReportContext = createContext<ComponentType | null>(null);
