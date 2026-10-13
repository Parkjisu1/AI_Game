import path from "node:path";
import { auth, authDisabled } from "@/auth";
import { timingSafeEqual } from "node:crypto";

export const assetDataRoot = process.env.PROJECTHUB_3D_DATA || path.join(process.cwd(), "data", "asset-studio");
export async function assetUser(req?: Request) {
  const expected = process.env.HERMES_INTERNAL_API_KEY || "";
  const supplied = req?.headers.get("x-hermes-key") || "";
  if (expected && supplied && Buffer.byteLength(expected) === Buffer.byteLength(supplied) && timingSafeEqual(Buffer.from(expected), Buffer.from(supplied))) return "hermes-internal";
  const session = await auth();
  return session?.user?.email || (authDisabled ? "local-dev" : null);
}
