import { Suspense } from "react";
import { LoginForm } from "@/components/auth/LoginForm";

export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md items-center px-6">
      <section className="w-full space-y-4">
        <h1 className="text-2xl font-bold text-stone-900">문서 아카이브 로그인</h1>
        <p className="text-sm text-stone-600">운영 계정으로 로그인한 뒤 대시보드에 접근할 수 있습니다.</p>
        <Suspense fallback={<p className="text-sm text-stone-500">로그인 폼 로딩 중...</p>}>
          <LoginForm />
        </Suspense>
      </section>
    </main>
  );
}
