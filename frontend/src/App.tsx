import ReviewScreen from "./review-screen/ReviewScreen";
import { useReviewSession } from "./review-screen/useReviewSession";
import "./review-screen/base.css";

export default function App() {
  const session = useReviewSession();
  return <ReviewScreen session={session} />;
}
