from pprint import pprint
# from parser.base import ParserBase
import os
import json
import glob
import gzip

import xmltodict


def get_patch_category(fp_len, pf_len, ff_len):
    patch_category = ""
    if fp_len > 0 and pf_len == 0 and ff_len == 0:
        patch_category = "PatchCategory.CleanFixFull"

    if fp_len > 0 and pf_len == 0 and ff_len > 0:
        patch_category = "PatchCategory.CleanFixPartial"

    if fp_len > 0 and pf_len > 0 and ff_len == 0:
        patch_category = "PatchCategory.NoisyFixFull"

    if fp_len > 0 and pf_len > 0 and ff_len > 0:
        patch_category = "PatchCategory.NoisyFixPartial"

    if fp_len == 0 and pf_len == 0 and ff_len > 0:
        patch_category = "PatchCategory.NoneFix"

    if fp_len == 0 and pf_len > 0 and ff_len > 0:
        patch_category = "PatchCategory.NegFix"

    return patch_category


class PraprParser():
    def __init__(self, prapr_dir, failing_test_dir, output_dir):
        self._prapr_dir = prapr_dir
        self._failing_test_dir = failing_test_dir
        self._output_dir = os.path.join(output_dir)
        self._Lang_version = [6, 7, 10, 22, 25, 26, 27, 31, 33, 39, 43, 44, 51, 57, 58, 59, 60, 61, 63]
        # self._Lang_version = [6]

        self._tool_name = "prapr"

        os.makedirs(self._output_dir, exist_ok=True)


    def _parse_original_failing_tests(self, version_id):
        test_filename = os.path.join(self._failing_test_dir, "{}.txt".format(version_id))
        failing_tests = set()

        with open(test_filename) as file:
            for line in file:
                failing_tests.add(line.rstrip("\n").replace("::", "."))
        return failing_tests


    def _read_prapr_report(self, version_id):
        version_str = str(version_id)
        prapr_report_root = os.path.join(self._prapr_dir, version_str, "target", "prapr-reports")
        gz_file_list = glob.glob(os.path.join(prapr_report_root, "**", "*.gz"))
        assert len(gz_file_list) == 1, "find more prapr reports"

        gz_file = gz_file_list[0]
        input = gzip.open(gz_file, 'r')
        prapr_dict = xmltodict.parse(input)
        mutation_list = prapr_dict["mutations"]["mutation"]

        mutation_dict = {}
        for id, mutation_i in enumerate(mutation_list):
            status = mutation_i["@status"]
            modified_method = "{}.{}{}".format(mutation_i["mutatedClass"], mutation_i["mutatedMethod"], mutation_i["methodDescription"])
            modified_line = mutation_i["lineNumber"]
            executed_tests = mutation_i["coveringTests"].split(", ")
            failed_tests = mutation_i["killingTests"].split(", ") if mutation_i["killingTests"] is not None else []

            executed_tests = [i.split("(")[0] for i in executed_tests]
            failed_tests = [i.split("(")[0] for i in failed_tests]

            sorted_failed_tests = []
            sorted_passed_tests = []

            for test_i in executed_tests:
                if test_i in failed_tests:
                    sorted_failed_tests.append(test_i)
                else:
                    sorted_passed_tests.append(test_i)
            
            sorted_executed_tests = sorted_failed_tests + sorted_passed_tests

            mutation_dict[id] = {
                "status": status,
                "modified_method": modified_method,
                "modified_line": modified_line,
                "executed_tests": sorted_executed_tests,
                "failed_tests": sorted_failed_tests,
            }

        return mutation_dict


    def _merge_result(self, failing_tests, mutation_dict):
        org_f_test_set = set(failing_tests)
        merged_result_dict = {}
        modified_method_set = set()

        for patch_id, patch_content in mutation_dict.items():
            patch_f_test_set = set(patch_content["failed_tests"])

            ff = org_f_test_set & patch_f_test_set
            fp = org_f_test_set - ff
            pf = patch_f_test_set - ff

            ff_len = len(ff)
            fp_len = len(fp)
            pf_len = len(pf)

            if patch_content["status"] in ['SURVIVED', 'KILLED']:
                patch_category = get_patch_category(fp_len, pf_len, ff_len)
            else:
                patch_category = "PatchCategory." + patch_content["status"]

            merged_result_dict[patch_id] = {
                "method": patch_content["modified_method"],
                "line": int(patch_content["modified_line"]),
                "pf_len": pf_len,
                "ff_len": ff_len,
                "fp_len": fp_len,
                "patch_category": patch_category,
            }
            modified_method_set.add(patch_content["modified_method"])
        
        modified_method_list = sorted(list(modified_method_set))
        method_id_dict = {}
        for id, method in enumerate(modified_method_list):
            method_id_dict[method] = id

        id_method_dict = {id: method for method, id in method_id_dict.items()}
        
        for patch_id, patch_content in merged_result_dict.items():
            patch_content["method"] = method_id_dict[patch_content["method"]]
        
        result = {
            "method": id_method_dict,
            "patch": merged_result_dict
        }

        return result


    def _truncate_test_excution(self, patch_dict):
        for _, patch_data in patch_dict.items():
            if len(patch_data["failed_tests"]) > 0:
                first_failed_test_id = patch_data["failed_tests"][0]
                first_failed_test_idx = patch_data["executed_tests"].index(first_failed_test_id)
                patch_data["executed_tests"] = patch_data["executed_tests"][: first_failed_test_idx + 1]


    def _run_project(self, version_id):
        failing_tests = self._parse_original_failing_tests(version_id)
        mutation_dict = self._read_prapr_report(version_id)
        full_result = self._merge_result(failing_tests, mutation_dict)

        self._truncate_test_excution(mutation_dict)
        partial_result = self._merge_result(failing_tests, mutation_dict)

        
        full_output_dir = os.path.join(self._output_dir, "full")
        partial_output_dir = os.path.join(self._output_dir, "partial")

        os.makedirs(full_output_dir, exist_ok=True)
        os.makedirs(partial_output_dir, exist_ok=True)

        full_output_filename = os.path.join(full_output_dir, "Lang_{}.json".format(version_id))
        partial_output_filename = os.path.join(partial_output_dir, "Lang_{}.json".format(version_id))
        
        with open(full_output_filename, 'w') as json_file:
            json.dump(full_result, json_file, indent=4)

        with open(partial_output_filename, 'w') as json_file:
            json.dump(partial_result, json_file, indent=4)
    

    def run_all_project(self):
        for version_id in self._Lang_version:
            try:
                print("processing {}".format(version_id))
                self._run_project(version_id)
            except:
                print("Error {}".format(version_id))


if __name__ == "__main__":
    prapr_dir = os.path.abspath("/filesystem/patch_ranking/SubjectPrograms/Lang4Test")
    failing_test_dir = "/filesystem/patch_ranking/ProflPartialMatrix/python/data/prapr/FailingTests/Lang"
    output_dir = os.path.abspath("/filesystem/patch_ranking/ProflPartialMatrix/python/data/prapr/lingming_data/output")

    pp = PraprParser(prapr_dir, failing_test_dir, output_dir)
    pp.run_all_project()