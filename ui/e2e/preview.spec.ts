import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// The preview (VITE_BACKEND_MODE=demo) runs the whole core loop in the browser, so this
// walks it end to end with no server: syllabus in, review, roadmap, approval, schedule.
const SYLLABUS = `CSC10014 Tư duy tính toán
CLO1: Phát biểu bài toán và phân rã thành các bài toán con
CLO2: Thiết kế thuật toán và đánh giá độ phức tạp
Tuần 1: Phân rã bài toán, Trừu tượng hóa
Tuần 2: Nhận diện mẫu hình, Thiết kế thuật toán
Tuần 3: Cấu trúc dữ liệu cơ bản
Tuần 4: Tìm kiếm và sắp xếp
Tuần 5: Đệ quy, Chia để trị
Tuần 6: Quy hoạch động
Đánh giá
Giữa kỳ: tuần 4 (30%)
Cuối kỳ: tuần 7 (70%)
Giáo trình
1. Computational Thinking, Peter Denning`;

const accessible = async (page: Page) =>
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);

async function toProposal(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Bắt đầu từ đề cương" })).toBeVisible();
  await page.getByRole("button", { name: "Dán nội dung" }).click();
  await page.getByLabel("Nội dung đề cương").fill(SYLLABUS);
  await page.getByRole("button", { name: "Đọc đề cương" }).click();
  await expect(page.getByRole("heading", { name: "Kiểm tra đề cương" })).toBeVisible();
}

test("a pasted syllabus becomes an approved roadmap and a schedule", async ({ page }) => {
  await page.goto("/");
  await accessible(page);
  await toProposal(page);
  await expect(page.getByRole("tab", { name: /Tuần và chủ đề/ })).toContainText("7");
  await accessible(page);

  // One button confirms the syllabus and proposes the roadmap.
  await page.getByRole("button", { name: "Xác nhận và tạo lộ trình" }).click();
  await expect(page.getByRole("heading", { name: "Lộ trình đề xuất" })).toBeVisible();
  await expect(page.getByText("10 bước học, 2 mốc kiểm tra")).toBeVisible();

  await page.getByRole("button", { name: /Tìm kiếm và sắp xếp/ }).click();
  const panel = page.getByRole("region", { name: "Chi tiết: Tìm kiếm và sắp xếp" });
  await expect(panel.getByRole("heading", { name: "Cần học trước" })).toBeVisible();
  await accessible(page);
  await panel.getByLabel("Thêm bước cần học trước").selectOption({ label: "Tuần 1: Phân rã bài toán" });
  await expect(panel.getByRole("button", { name: "Phân rã bài toán", exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "Đóng chi tiết" }).click();

  await page.getByRole("button", { name: "Sơ đồ" }).click();
  await expect(page.getByRole("button", { name: /Mốc kiểm tra: Giữa kỳ/ })).toBeVisible();
  await accessible(page);

  await page.getByRole("button", { name: "Duyệt lộ trình" }).click();
  await expect(page.getByRole("heading", { name: "CSC10014 Tư duy tính toán" })).toBeVisible();
  await expect(page.getByText("0/10 bước đã xong")).toBeVisible();
  await accessible(page);

  // The preview keeps the course for this tab, so a reload does not start over.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Tiếp theo: tuần 1" })).toBeVisible();

  await page.goto("/#schedule");
  await page.getByRole("button", { name: "Xếp lộ trình vào lịch" }).click();
  await expect(page.getByRole("heading", { name: "10 buổi học" })).toBeVisible();
  await accessible(page);
});

test("a prerequisite that would close a loop is refused with a reason", async ({ page }) => {
  await toProposal(page);
  await page.getByRole("button", { name: "Xác nhận và tạo lộ trình" }).click();
  // Week order already puts "Trừu tượng hóa" before "Nhận diện mẫu hình".
  await page.getByRole("button", { name: /Trừu tượng hóa/ }).click();
  const panel = page.getByRole("region", { name: "Chi tiết: Trừu tượng hóa" });
  await panel.getByLabel("Thêm bước cần học trước").selectOption({ label: "Tuần 2: Nhận diện mẫu hình" });
  await expect(panel.getByRole("alert")).toContainText("vòng lặp");
});

test("the graph can be walked with the arrow keys", async ({ page }) => {
  await toProposal(page);
  await page.getByRole("button", { name: "Xác nhận và tạo lộ trình" }).click();
  await page.getByRole("button", { name: "Sơ đồ" }).click();
  await page.getByRole("button", { name: /Bước: Phân rã bài toán/ }).focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Chi tiết: Thiết kế thuật toán" })).toBeVisible();
});

test("dark theme is remembered and still passes the accessibility scan", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Cài đặt" }).filter({ visible: true }).click();
  await page.getByRole("button", { name: "Tối" }).click();
  await page.getByRole("button", { name: "Đóng" }).click();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await accessible(page);
});
