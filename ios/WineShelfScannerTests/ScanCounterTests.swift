import XCTest
@testable import WineShelfScanner

final class ScanCounterTests: XCTestCase {

    private let suiteName = "ScanCounterTests"
    private var defaults: UserDefaults!
    private var currentDate: Date!
    private var counter: ScanCounter!

    override func setUp() {
        super.setUp()
        defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        currentDate = date(2026, 7, 15)
        counter = ScanCounter(defaults: defaults, now: { self.currentDate })
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        counter = nil
        super.tearDown()
    }

    private func date(_ year: Int, _ month: Int, _ day: Int) -> Date {
        Calendar.current.date(from: DateComponents(year: year, month: month, day: day, hour: 12))!
    }

    // MARK: - Counting Within a Month

    func testStartsAtZero() {
        XCTAssertEqual(counter.count, 0)
        XCTAssertEqual(counter.remaining, ScanCounter.freeLimit)
        XCTAssertFalse(counter.hasReachedLimit)
    }

    func testIncrementPersistsWithinMonth() {
        counter.increment()
        counter.increment()
        counter.increment()

        XCTAssertEqual(counter.count, 3)
        XCTAssertEqual(counter.remaining, 2)

        // A fresh instance reading the same store sees the same count
        let reloaded = ScanCounter(defaults: defaults, now: { self.currentDate })
        XCTAssertEqual(reloaded.count, 3)
    }

    func testBlocksAtFiveWithinOneMonth() {
        for _ in 0..<4 {
            counter.increment()
        }
        XCTAssertFalse(counter.hasReachedLimit)

        counter.increment()

        XCTAssertEqual(counter.count, 5)
        XCTAssertEqual(counter.remaining, 0)
        XCTAssertTrue(counter.hasReachedLimit)
    }

    func testCountPersistsAcrossDaysInSameMonth() {
        counter.increment()
        counter.increment()

        currentDate = date(2026, 7, 31)

        XCTAssertEqual(counter.count, 2)
    }

    // MARK: - Monthly Reset

    func testResetsAcrossMonthBoundary() {
        for _ in 0..<5 {
            counter.increment()
        }
        XCTAssertTrue(counter.hasReachedLimit)

        // Calendar flips to August
        currentDate = date(2026, 8, 1)

        XCTAssertEqual(counter.count, 0)
        XCTAssertEqual(counter.remaining, ScanCounter.freeLimit)
        XCTAssertFalse(counter.hasReachedLimit)
    }

    func testIncrementAfterMonthChangeStartsFresh() {
        for _ in 0..<5 {
            counter.increment()
        }
        currentDate = date(2026, 8, 3)

        counter.increment()

        XCTAssertEqual(counter.count, 1)
        XCTAssertFalse(counter.hasReachedLimit)
    }

    func testResetsAcrossYearBoundary() {
        currentDate = date(2026, 12, 31)
        counter.increment()
        XCTAssertEqual(counter.count, 1)

        currentDate = date(2027, 1, 1)
        XCTAssertEqual(counter.count, 0)
    }

    // MARK: - Period Key

    func testPeriodKeyFormat() {
        XCTAssertEqual(ScanCounter.periodKey(for: date(2026, 7, 15)), "2026-07")
        XCTAssertEqual(ScanCounter.periodKey(for: date(2026, 1, 1)), "2026-01")
        XCTAssertEqual(ScanCounter.periodKey(for: date(2026, 12, 31)), "2026-12")
    }

    // MARK: - Reset

    func testResetClearsCount() {
        counter.increment()
        counter.increment()

        counter.reset()

        XCTAssertEqual(counter.count, 0)
    }
}
