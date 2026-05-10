export default function Loading() {
  return (
    <main className="container mx-auto py-12 max-w-3xl">
      <div className="animate-pulse space-y-4">
        <div className="h-4 w-20 rounded bg-muted" />
        <div className="h-10 w-64 rounded bg-muted" />
        <div className="h-4 w-full rounded bg-muted" />
        <div className="mt-8 h-40 rounded-lg border bg-muted" />
      </div>
    </main>
  );
}
