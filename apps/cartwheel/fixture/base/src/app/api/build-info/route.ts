export const dynamic = "force-dynamic";

export function GET(): Response {
  const sourceSha = process.env.CARTWHEEL_BUILD_SOURCE_SHA;
  const headers = { "cache-control": "no-store, max-age=0" };
  if (!sourceSha || !/^[0-9a-f]{40}$/.test(sourceSha)) {
    return Response.json({ error: "build identity unavailable" }, { status: 503, headers });
  }
  return Response.json({ schema_version: "1.0", source_sha: sourceSha }, { headers });
}
