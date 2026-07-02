import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", () => ({
  API_BASE: "/api",
  apiFetch: apiFetchMock,
}));

import { fetchLibraryPage } from "./useLibrary";

const libraryPage = {
  works: [
    {
      document_id: "doc-1",
      title: "Readable Work",
      author: "Ada",
      servability: "public_domain",
      servable_full_text: true,
      page_count: 12,
      cover_uri: null,
      ip_holder_id: null,
      taken_down: false,
    },
  ],
  total: 1,
  page: 2,
  page_size: 12,
};

beforeEach(() => {
  apiFetchMock.mockReset();
});

describe("fetchLibraryPage", () => {
  it("queries the registered catalog route with filter, search, page, and page_size", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(libraryPage), { status: 200 }),
    );

    const page = await fetchLibraryPage({
      filter: "gated",
      search: "A Study & Notes",
      page: 2,
      pageSize: 12,
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const url = apiFetchMock.mock.calls[0][0] as string;
    expect(url).toBe(
      "/api/library?filter=gated&search=A+Study+%26+Notes&page=2&page_size=12",
    );
    expect(page).toEqual(libraryPage);
  });

  it("uses the backend default page size mirror when pageSize is omitted", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ...libraryPage, page_size: 20 }), { status: 200 }),
    );

    await fetchLibraryPage({ filter: "servable", search: "", page: 1 });

    expect(apiFetchMock.mock.calls[0][0]).toBe(
      "/api/library?filter=servable&search=&page=1&page_size=20",
    );
  });

  it("sanitizes catalog works and pagination before rendering the shelf", async () => {
    apiFetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          works: [
            {
              document_id: "  doc-1  ",
              title: "  Readable Work  ",
              author: "  Ada  ",
              servability: "future_open",
              servable_full_text: true,
              page_count: "12",
              cover_uri: "  https://example.test/cover.png  ",
              ip_holder_id: 42,
              taken_down: false,
            },
            {
              document_id: " ",
              title: "Missing identity",
              servability: "public_domain",
              servable_full_text: true,
            },
          ],
          total: "2",
          page: "2",
          page_size: "12",
        }),
        { status: 200 },
      ),
    );

    await expect(
      fetchLibraryPage({ filter: "all", search: "", page: 2, pageSize: 12 }),
    ).resolves.toEqual({
      works: [
        {
          document_id: "doc-1",
          title: "Readable Work",
          author: "Ada",
          servability: "gated_metadata_only",
          servable_full_text: false,
          page_count: 0,
          cover_uri: "https://example.test/cover.png",
          ip_holder_id: null,
          taken_down: false,
        },
      ],
      total: 1,
      page: 2,
      page_size: 12,
    });
  });

  it("turns a 404 into the route-absent sentinel, not an empty page", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("not found", { status: 404 }));

    await expect(
      fetchLibraryPage({ filter: "all", search: "", page: 1, pageSize: 24 }),
    ).rejects.toThrow("library_route_absent");
  });

  it("keeps unexpected failures loud with the endpoint name", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("boom", { status: 500 }));

    await expect(
      fetchLibraryPage({ filter: "all", search: "", page: 1, pageSize: 24 }),
    ).rejects.toThrow("GET /library: HTTP 500");
  });
});
