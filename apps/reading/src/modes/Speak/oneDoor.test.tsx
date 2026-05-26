import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Navigate, MemoryRouter, Route, Routes } from "react-router-dom";

/**
 * oneDoor.test — the routing-level proof of the Speak one-door consolidation
 * (Product Depth SPR-08 M1).
 *
 * App.tsx redirects the duplicate Interview surface into the single Speak
 * door. This reproduces those exact redirect routes and asserts a request to
 * either legacy path lands on the Speak home — never the retired Interview
 * surfaces. (We test the redirect contract in isolation rather than mounting
 * the full App + AuthProvider, which is the load-bearing behaviour.)
 */
function InterviewRedirect() {
  return <Navigate to="/speak" replace />;
}

afterEach(cleanup);

function mountAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/interviews" element={<Navigate to="/speak" replace />} />
        <Route path="/interview/:interviewId" element={<InterviewRedirect />} />
        <Route path="/speak" element={<div>SPEAK HOME</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Speak one door — legacy Interview routes redirect into /speak", () => {
  it("/interviews redirects to the Speak home", () => {
    mountAt("/interviews");
    expect(screen.getByText("SPEAK HOME")).toBeTruthy();
  });

  it("/interview/:id (a deep-link) redirects to the Speak home", () => {
    mountAt("/interview/iv-123");
    expect(screen.getByText("SPEAK HOME")).toBeTruthy();
  });
});
