import { useCallback, useState } from "react";
export const draftKey = (sessionId: string) => `tess.unsent.v1.${sessionId}`;
export function useDraftText(sessionId: string) {
  const [text, setText] = useState(
    () => localStorage.getItem(draftKey(sessionId)) || "",
  );
  const update = useCallback(
    (value: string) => {
      localStorage.setItem(draftKey(sessionId), value);
      setText(value);
    },
    [sessionId],
  );
  return [text, update] as const;
}
