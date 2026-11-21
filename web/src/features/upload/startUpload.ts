/** Shared by the upload form and the AI interview: ask for a signed URL and register the app-level upload job. */
import { unwrap, type ApiClient } from "../../api/client";
import { fileExtension } from "./precheck";
import { registerJob, UploadJob } from "./uploader";

/** `POST /sessions/{id}/audio` then register (not start) the job; the caller starts it, then opens the session page. */
export async function prepareUpload(client: ApiClient, id: string, f: File): Promise<void> {
  const request = async () =>
    unwrap(
      await client.POST("/sessions/{id}/audio", {
        params: { path: { id } },
        body: { content_type: f.type, size_bytes: f.size, filename_ext: fileExtension(f.name) },
      }),
    );
  const first = await request();
  registerJob(
    id,
    new UploadJob({
      file: f,
      first,
      requestTarget: request,
      complete: async () =>
        unwrap(await client.POST("/sessions/{id}/audio/complete", { params: { path: { id } } })),
    }),
  );
}
