import ReviewScreen from "./us7/ReviewScreen";
import { useReviewSession } from "./us7/useReviewSession";
import "./us7/base.css";

export default function App() {
  const session = useReviewSession();
  return <ReviewScreen session={session} />;
}
