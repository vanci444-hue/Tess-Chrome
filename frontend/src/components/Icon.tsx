/** 图标来自桌面 icon 套件，只用到的文件才复制进 src/assets/icons。 */
import refresh from "../assets/icons/arrow-refresh-01.svg?raw";
import microphone from "../assets/icons/microphone-01.svg?raw";
import close from "../assets/icons/x-02.svg?raw";
import check from "../assets/icons/check.svg?raw";
import send from "../assets/icons/arrow-up.svg?raw";
import history from "../assets/icons/file-06.svg?raw";
import plans from "../assets/icons/file-check-01.svg?raw";
import back from "../assets/icons/arrow-left.svg?raw";
import plus from "../assets/icons/plus-01.svg?raw";

const catalog = {
  refresh,
  microphone,
  close,
  check,
  send,
  history,
  plans,
  back,
  plus,
} as const;

export type IconName = keyof typeof catalog;

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <span
      className="ui-icon"
      aria-hidden="true"
      dangerouslySetInnerHTML={{
        __html: catalog[name]
          .replace(/\swidth="24"/, ` width="${size}"`)
          .replace(/\sheight="24"/, ` height="${size}"`),
      }}
    />
  );
}
