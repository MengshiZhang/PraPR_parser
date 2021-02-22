import os
import json
from pprint import pprint


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


class PraPRParser:
    def __init__(self, data_dir, output_dir, project_list=["Mockito"]):
        self._data_dir = data_dir
        self._output_dir = output_dir
        self.project_list = project_list
        self.separator = "^^^^^"

    
    def _parse_test_log(self, test_log_filename):
        test_dict = {}

        with open(test_log_filename) as file:
            for line in file:
                test_name, test_id, test_result = line.rstrip("\n").split(" ")
                test_dict[int(test_id)] = {
                    "test": test_name,
                    "test_result": test_result,
                }

        return test_dict


    def _parse_mutant_log(self, mutant_log_filename):
        def parse_tests(test_str):
            test_ids = [int(i) for i in test_str.lstrip(" ").rstrip(" \n").split(" ") if len(i) > 0]
            return test_ids

        patch_dict = {}
        with open(mutant_log_filename) as file:
            patch_id = 0
            for line in file:
                if self.separator in line:
                    tag, mutator, method, testOrder, testFail = line.split(self.separator)
                    modified_line_num = int(tag.split(":")[-1])
                    test_execution_list = parse_tests(testOrder)
                    failed_test_list = parse_tests(testFail)

                    patch_dict[patch_id] = {
                        "method": method,
                        "line": modified_line_num,
                        "test_execution_list": test_execution_list,
                        "failed_test_list": failed_test_list,
                    }

                    patch_id += 1

        return patch_dict


    def _merge_result(self, patch_dict, test_dict):
        merged_result_dict = {}
        method_id_mapping = {}
        id_method_mapping = {}

        for patch_id, patch_data in patch_dict.items():
            pf, pp, ff, fp = [0, 0, 0, 0]
            for executed_test_id in patch_data["test_execution_list"]:
                org_test_result = test_dict[executed_test_id]["test_result"]
                if org_test_result == "P":
                    if executed_test_id in patch_data["failed_test_list"]:
                        pf += 1
                    else:
                        pp += 1

                if org_test_result == "F":
                    if executed_test_id in patch_data["failed_test_list"]:
                        ff += 1
                    else:
                        fp += 1

            method_str = patch_data["method"]
            if method_str not in method_id_mapping:
                method_id = len(method_id_mapping.keys())
                method_id_mapping[method_str] = method_id
                id_method_mapping[method_id] = method_str

            merged_result_dict[patch_id] = {
                "method": method_id_mapping[method_str],
                "line": patch_data["line"],
                "pf_len": pf,
                "pp_len": pp,
                "ff_len": ff,
                "fp_len": fp,
                "patch_category": get_patch_category(fp, pf, ff),
            }

        return merged_result_dict, id_method_mapping

    
    def _truncate_test_excution(self, patch_dict):
        for patch_id, patch_data in patch_dict.items():
            if len(patch_data["failed_test_list"]) > 0:
                first_failed_test_id = patch_data["failed_test_list"][0]
                first_failed_test_idx = patch_data["test_execution_list"].index(first_failed_test_id)
                patch_data["test_execution_list"] = patch_data["test_execution_list"][: first_failed_test_idx + 1]


    def parse_version_i(self, project, version):
        print("processing {} - {}".format(project, version))

        mutant_log_filename = os.path.join(self._data_dir, project, "{}_mutantlog".format(version))
        test_log_filename = os.path.join(self._data_dir, project, "{}_testLog".format(version))

        patch_dict = self._parse_mutant_log(mutant_log_filename)
        test_dict = self._parse_test_log(test_log_filename)

        merged_result_dict, id_method_mapping = self._merge_result(patch_dict, test_dict)
        
        # save full result
        full_output_dir = os.path.join(self._output_dir, "full")
        os.makedirs(full_output_dir, exist_ok=True)
        full_output_filename = os.path.join(full_output_dir, "{}_{}.json".format(project, version))

        with open(full_output_filename, 'w') as json_file:
            json.dump({
                "patch": merged_result_dict,
                "method": id_method_mapping,
                "test": test_dict,
            }, json_file, indent=4)
        

        # save partial result
        partial_output_dir = os.path.join(self._output_dir, "partial")
        os.makedirs(partial_output_dir, exist_ok=True)
        partial_output_filename = os.path.join(partial_output_dir, "{}_{}.json".format(project, version))

        self._truncate_test_excution(patch_dict)
        merged_result_dict, id_method_mapping = self._merge_result(patch_dict, test_dict)

        with open(partial_output_filename, 'w') as json_file:
            json.dump({
                "patch": merged_result_dict,
                "method": id_method_mapping,
                "test": test_dict,
            }, json_file, indent=4)
    

    def process_all(self):
        for project in self.project_list:
            project_dir = os.path.join(self._data_dir, project)
            version_list = [int(i.replace("_testLog", "")) for i in os.listdir(project_dir) if i.endswith("_testLog")]
            for version in version_list:
                self.parse_version_i(project, version)

            # print(version_list)


if __name__ == "__main__":
    data_dir = "/filesystem/patch_ranking/ProflPartialMatrix/python/data/prapr/yiling_data"
    output_dir = "output"
    project_list = ["Mockito"]
    pp = PraPRParser(data_dir, output_dir, project_list)
    pp.process_all()

