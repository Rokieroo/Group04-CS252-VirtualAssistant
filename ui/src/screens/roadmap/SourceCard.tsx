import type { ReactNode } from "react";
import { duration } from "../../app/text";
import { Icon } from "../../ui/icons";
import { Chip } from "../../ui/kit";

const formats: Record<string, string> = {
  article: "Bài viết",
  video: "Video",
  course: "Khóa học",
  book: "Sách",
  paper: "Bài báo",
  exercise: "Bài tập",
  slides: "Bài giảng",
};

/**
 * One learning source. Only a catalog source that passed review may say "Đã kiểm chứng";
 * a web result never does, however good it looks.
 */
export function SourceCard({
  title,
  url,
  from,
  format,
  minutes,
  license,
  reason,
  verified,
  children,
}: {
  title: string;
  url: string | null;
  /** Institution or provider that published it. */
  from?: string | null;
  format?: string;
  minutes?: number | null;
  license?: string | null;
  reason?: string;
  verified?: boolean;
  children?: ReactNode;
}) {
  return (
    <article className="source">
      <h4>
        {url ? (
          <a href={url} target="_blank" rel="noreferrer">
            {title}
            <Icon name="external" size={14} />
            <span className="sr-only"> (mở trong thẻ mới)</span>
          </a>
        ) : (
          title
        )}
      </h4>
      {from && <p className="muted small">{from}</p>}
      <div className="row source-tags">
        {verified && (
          <Chip tone="route">
            <Icon name="check" size={12} />
            Đã kiểm chứng
          </Chip>
        )}
        {format && <Chip>{formats[format.toLowerCase()] ?? format}</Chip>}
        {minutes ? <Chip>{duration(minutes)}</Chip> : null}
        {license && <Chip title="Giấy phép sử dụng">{license}</Chip>}
      </div>
      {reason && <p className="small">{reason}</p>}
      {children && <div className="row">{children}</div>}
    </article>
  );
}
