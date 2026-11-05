import { Link } from 'react-router-dom'
import { PageHeader } from '../components/Panel'

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Page not found" lede="That address does not match any screen in this console." />
      <Link to="/">Back to the overview</Link>
    </>
  )
}
