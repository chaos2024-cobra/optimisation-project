import unittest
from dataclasses import replace

from replan import enumerate_reference, greedy, metrics, milp, milp_reference, scenario
from validate import DATA, load_instance, repair, validate


class TestReplanning(unittest.TestCase):
    def test_demo_preserves_routine_coverage(self):
        case = scenario()
        plan, unlocked, fallback = repair(case)
        self.assertEqual(metrics(case, greedy(case)), (0, 23, 0, -8))
        self.assertEqual(metrics(case, plan), (15, 23, -3, -11))
        self.assertEqual(unlocked, 3)
        self.assertFalse(fallback)
        self.assertEqual(metrics(case, plan), metrics(case, enumerate_reference(case)))

    def test_deadline_infeasible(self):
        case = replace(scenario(), deadline=10)
        plan, unlocked, fallback = repair(case)
        self.assertEqual(metrics(case, plan), (0, 23, 0, -8))
        self.assertEqual(unlocked, 0)
        self.assertFalse(fallback)

    @unittest.skipIf(milp is None, "SciPy required")
    def test_milp_agrees_with_independent_enumeration(self):
        for deadline in (10, 11, 12, 16):
            with self.subTest(deadline=deadline):
                case = replace(scenario(), deadline=deadline)
                plan = milp_reference(case)
                validate(case, plan, {p.id: (p.start, p.end) for p in case.passes})
                self.assertEqual(metrics(case, plan), metrics(case, enumerate_reference(case)))

    def test_bundled_benchmark_dimensions(self):
        expected = {"T200_S3_G1_H1": 184, "T200_S3_G1_H2": 362, "T400_S3_G1_H1": 371}
        for name, count in expected.items():
            with self.subTest(instance=name):
                passes, bounds, _, duration = load_instance(DATA / (name + ".inst"))
                self.assertEqual(len(passes), count)
                self.assertEqual(len({p.satellite for p in passes}), 3)
                self.assertEqual(duration, 30)
                for p in passes:
                    self.assertLessEqual(bounds[p.id][0], p.start)
                    self.assertLessEqual(p.end, bounds[p.id][1])


if __name__ == "__main__":
    unittest.main()
