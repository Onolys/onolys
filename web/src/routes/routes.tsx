import { Navigate, type RouteObject } from "react-router";
import { AuthAction } from "../auth/pages/AuthAction";
import { ForgotPassword } from "../auth/pages/ForgotPassword";
import { Login } from "../auth/pages/Login";
import { Signup } from "../auth/pages/Signup";
import { VerifyEmail } from "../auth/pages/VerifyEmail";
import { PublicOnly, RequireUnverified, RequireVerified } from "../auth/guards";
import { NewSessionChooser } from "../features/dashboard/NewSessionChooser";
import { SessionsPage } from "../features/dashboard/SessionsPage";
import { SampleReportPage } from "../features/report/SampleReportPage";
import { ReportPage } from "../features/report/ReportPage";
import { InterviewPage } from "../features/interview/InterviewPage";
import { NewInterviewPage } from "../features/interview/NewInterviewPage";
import { NewSessionPage } from "../features/upload/NewSessionPage";
import { SessionPage } from "../features/session/SessionPage";
import { PrivacyPolicy } from "../features/legal/PrivacyPolicy";
import { Terms } from "../features/legal/Terms";
import { Layout } from "./Layout";
import { RouteError } from "./RouteError";
import { Settings } from "../features/settings/Settings";
import * as P from "./placeholders";

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      {
        errorElement: <RouteError />,
        children: [
        { path: "/", element: <Navigate to="/new" replace /> },
        {
          element: <PublicOnly />,
          children: [
            { path: "/signup", element: <Signup /> },
            { path: "/login", element: <Login /> },
            { path: "/forgot-password", element: <ForgotPassword /> },
          ],
        },
        { element: <RequireUnverified />, children: [{ path: "/verify-email", element: <VerifyEmail /> }] },
        {
          element: <RequireVerified />,
          children: [
            { path: "/new", element: <NewSessionChooser /> },
            { path: "/sessions", element: <SessionsPage /> },
            { path: "/sessions/new", element: <NewSessionPage /> },
            { path: "/interviews/new", element: <NewInterviewPage /> },
            { path: "/interviews/:id", element: <InterviewPage /> },
            { path: "/sessions/:id", element: <SessionPage /> },
            { path: "/sessions/:id/reports/:version", element: <ReportPage /> },
            { path: "/settings", element: <Settings /> },
          ],
        },
        // Email action links (verify email, reset password): reachable in every auth state, so no guard.
        { path: "/auth/action", element: <AuthAction /> },
        { path: "/privacy", element: <PrivacyPolicy /> },
        { path: "/terms", element: <Terms /> },
        { path: "/sample", element: <SampleReportPage /> },
        { path: "/sample-report", element: <Navigate to="/sample" replace /> },
        { path: "*", element: <P.NotFound /> },
        ],
      },
    ],
  },
];
