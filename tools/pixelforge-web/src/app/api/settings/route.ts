import { NextRequest, NextResponse } from "next/server";

// 런타임에 API 키 업데이트 (메모리 + env)
let runtimeApiKey = process.env.PIXELLAB_API_KEY || "";

export async function POST(req: NextRequest) {
  const { pixellab_api_key } = await req.json();
  if (pixellab_api_key) {
    runtimeApiKey = pixellab_api_key;
    process.env.PIXELLAB_API_KEY = pixellab_api_key;
  }
  return NextResponse.json({ ok: true });
}

export async function GET() {
  return NextResponse.json({
    has_key: !!runtimeApiKey,
    key_preview: runtimeApiKey ? runtimeApiKey.substring(0, 8) + "..." : "",
  });
}
