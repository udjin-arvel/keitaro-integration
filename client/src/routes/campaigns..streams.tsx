import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/campaigns/streams')({
  component: RouteComponent,
})

function RouteComponent() {
  return <div>Hello "/campaigns/streams"!</div>
}
