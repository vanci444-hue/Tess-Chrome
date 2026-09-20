import { tess } from "../services/tess";
import { JIA_PROFILE } from "./demoCrm";

export async function ensureJiaSession(): Promise<string> {
  const listed = await tess.customers(JIA_PROFILE.nickname);
  const existing =
    listed.items.find((c) => c.nickname === JIA_PROFILE.nickname) ||
    listed.items[0];
  if (existing?.latest_session_id) return existing.latest_session_id;
  if (existing) {
    const session = await tess.newSession(existing.id);
    return session.id;
  }
  const customer = await tess.createCustomer({
    nickname: JIA_PROFILE.nickname,
    phone: JIA_PROFILE.phone,
    email: JIA_PROFILE.email,
    allow_duplicate: true,
    identity_confirmed: true,
  });
  const session = await tess.newSession(customer.id);
  return session.id;
}
