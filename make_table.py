import os
import json
from pprint import pprint


def get_table(data_path):
    result_dict = {
        "Overall": {
            "total_gt": 0,
            "total_eval": 0
        }
    }
    word_list = [i.replace(".json", "") for i in os.listdir(data_path) if i.endswith(".json")]
    for word in word_list:
        project, version = word.split("_")
        json_filename = os.path.join(data_path, "{}.json".format(word))

        with open(json_filename) as file:
            rerank_data = json.load(file)

        print("{} - {}".format(project, version))
        print("   gt: " + str(rerank_data["gt"]))
        print("   eval: " + str(rerank_data["eval"]))
        
        if project not in result_dict:
            result_dict[project] = {
                "total_gt": 0,
                "total_eval": 0
            }
        result_dict[project]["total_gt"] += rerank_data["gt"]
        result_dict[project]["total_eval"] += rerank_data["eval"]

        result_dict["Overall"]["total_gt"] += rerank_data["gt"]
        result_dict["Overall"]["total_eval"] += rerank_data["eval"]

        for project, proj_data in result_dict.items():
            a = proj_data["total_gt"]
            b = proj_data["total_eval"]
            improvement = (a - b) / a
            proj_data["imprv_ratio"] = improvement

    return result_dict


# with open("table.csv", "w") as file:
#     first_line_wrote = False

#     for data_path in [
#         "eval/full",
#         "eval/partial",
#         "eval_nononfix/full",
#         "eval_nononfix/partial",
#     ]:
#         result = get_table(data_path)

#         project_list = sorted(result.keys()) + ["Overall"]
#         if not first_line_wrote:
#             file.write(",{}\n".format(",".join(project_list)))
#             first_line_wrote = True

#         improvement_list = [str(result[i]["imprv_ratio"]) for i in project_list]
#         file.write("{},{}\n".format(data_path, ",".join(improvement_list)))


with open("table_3.csv", "w") as file:
    first_line_wrote = False

    # for data_path in [
    #     "eval/full",
    #     "eval/partial",
    #     "eval_nononfix/full",
    #     "eval_nononfix/partial",
    # ]:

    for data_path in [
        # "eval_no_closure_class_nononfix/partial",
        # "eval_no_closure_method_nononfix/partial",
        # "eval_no_closure_package_nononfix/partial",
        # "eval_no_closure_statement_nononfix/partial",
        # "eval_no_closure_no_negative_class_nononfix/partial",
        # "eval_no_closure_no_negative_method_nononfix/partial",
        # "eval_no_closure_no_negative_package_nononfix/partial",
        # "eval_no_closure_no_negative_statement_nononfix/partial",
        # "eval_no_closure_pf_negative_class_nononfix/partial",
        # "eval_no_closure_pf_negative_method_nononfix/partial",
        # "eval_no_closure_pf_negative_package_nononfix/partial",
        # "eval_no_closure_pf_negative_statement_nononfix/partial",
        # "eval_no_closure_method_fixbug_nononfix/partial",
        # "eval_no_closure_method_fixbug/partial",
        # "eval_no_closure_method_fixbug_pfBAD/partial",
        # "eval_no_closure_method_fixbug_pfBAD_NoneFixNo/partial",
        # "eval_no_closure_method_fixbug_pfBAD_NoneFixNoNegFixno/partial",
        # "eval_no_closure_method_fixbug_pfNone_NoneFixNoNegFixno/partial",
        # "eval_no_closure_method_fixbug_pfNone_NoneFixNoNegFixno_cleandata/partial",
        # "eval_no_closure_method_fixbug_pfNone_cleandata/partial",
        # "eval_no_closure_method_fixbug_pfNone_NoneFixNoNegFixnoxxx/partial",
        # "eval_no_closure_method_fixbug_pfNone_NoneFixNoxxx/partial"
        "eval_package/partial",
        "eval_class/partial",
        "eval_method/partial",
        "eval_statement/partial",
        "eval_package/full",
        "eval_class/full",
        "eval_method/full",
        "eval_statement/full"
    ]:
        result = get_table(data_path)
        # break

        project_list = sorted(result.keys())
        if not first_line_wrote:
            file.write(",{}\n".format(",".join(project_list)))
            first_line_wrote = True

        improvement_list = [str(result[i]["imprv_ratio"]) for i in project_list]
        file.write("{},{}\n".format(data_path, ",".join(improvement_list)))

