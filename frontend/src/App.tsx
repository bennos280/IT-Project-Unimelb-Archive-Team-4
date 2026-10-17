import ImportScreen from "./import/ImportScreen";
import ReviewScreen from "./review-screen/ReviewScreen";
import { useReviewSession } from "./review-screen/useReviewSession";
import ProgressDashboard from "./progress/ProgressDashboard";
import "./review-screen/base.css";

// Mount the review session only on survey URLs, avoiding API calls on the dashboard.
function SurveyReview() {
  const session = useReviewSession();
  return <><a className="review-dashboard-link" href="/">← Back to all bundles</a><ReviewScreen session={session}/></>;
}
export default function App() {
  if (new URLSearchParams(location.search).get("view") === "import") return <ImportScreen/>;
  return new URLSearchParams(location.search).has("survey") ? <SurveyReview/> : <ProgressDashboard/>;
}
