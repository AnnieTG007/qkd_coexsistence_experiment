from tqdm import tqdm
import time

def countdown(cd_time):
    for t in tqdm(range(cd_time, 0, -1), desc=f'倒计时{cd_time}秒', unit="秒", leave=False):
        time.sleep(1)
    # print("倒计时" + str(cd_time) + "秒结束！")
    return
