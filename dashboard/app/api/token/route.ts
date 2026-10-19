import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export async function GET(req: NextRequest) {
  // Only allow same-origin loopback requests to prevent CSRF token exfiltration
  const host = req.headers.get("host") || "";
  const secFetchSite = req.headers.get("sec-fetch-site");

  if (secFetchSite && secFetchSite === "cross-site") {
    return NextResponse.json({ error: "Forbidden: cross-site access prohibited" }, { status: 403 });
  }

  if (!host.startsWith("localhost:") && !host.startsWith("127.0.0.1:")) {
    return NextResponse.json({ error: "Forbidden: local only" }, { status: 403 });
  }

  try {
    const tokenPath = path.resolve(process.cwd(), "..", "data", "api_token");
    if (!fs.existsSync(tokenPath)) {
      return NextResponse.json({ token: null }, { status: 404 });
    }
    const token = fs.readFileSync(tokenPath, "utf8").trim();
    return NextResponse.json({ token });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
