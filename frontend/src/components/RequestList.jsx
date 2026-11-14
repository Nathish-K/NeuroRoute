import RequestListItem from "./RequestListItem";

function RequestList({ requests, onSelect }) {
  if (requests.length === 0) {
    return <p>No requests have been submitted.</p>;
  }

  return (
    <ul>
      {requests.map((request) => (
        <RequestListItem key={request.id} request={request} onSelect={onSelect} />
      ))}
    </ul>
  );
}

export default RequestList;
