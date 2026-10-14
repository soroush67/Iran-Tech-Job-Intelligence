import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-2 p-4 text-center">
      <h1 className="text-xl font-bold">صفحه پیدا نشد</h1>
      <Link href="/" className="text-primary underline">بازگشت به داشبورد</Link>
    </div>
  );
}
