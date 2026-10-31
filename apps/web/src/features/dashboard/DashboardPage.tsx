export interface DashboardPageProps {
  readonly initialParticipantId?: string;
  readonly initialTab?: string;
  readonly fetchImpl?: typeof fetch;
}

export function DashboardPage(_props: DashboardPageProps): React.JSX.Element {
  return <div>Dashboard</div>;
}
