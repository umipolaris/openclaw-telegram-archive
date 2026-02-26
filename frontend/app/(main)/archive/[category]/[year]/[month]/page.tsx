import { redirect } from "next/navigation";

interface PageProps {
  params: { category: string; year: string; month: string };
}

export default function ArchiveByMonthPage({ params }: PageProps) {
  const query = new URLSearchParams({
    category: params.category,
    year: params.year,
    month: params.month,
  });
  redirect(`/archive?${query.toString()}`);
}
