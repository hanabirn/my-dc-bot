# google_search.py

BEAUTY_IMAGES = [
    'https://pbs.twimg.com/media/HMtau3nb0AAUIVv?format=jpg&name=small',
    'https://pbs.twimg.com/media/HMr3gPhaIAAahDW?format=jpg&name=small',
    'https://pbs.twimg.com/media/HKc52-jbMAAXZOU?format=jpg&name=small', 
    'https://pbs.twimg.com/media/HMryh3rakAAJyEN?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNF73LsaoAADdE0?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNAQuOjbEAAR4ec?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNBNGyQbgAAVKm9?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNGRt5ua0AAPxgq?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNBOprKbAAAmxNG?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNF5pgia4AAJt2O?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNB6SAJa0AAATiT?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNE3V80aoAE8j3G?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNEJ5pQboAAbiNB?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNBJR4sbgAEKyIx?format=jpg&name=small',
    'https://pbs.twimg.com/media/HND8FcSawAAfpEX?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNBsSzGa0AA1RNC?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNHga01bUAAqX1-?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNDAehKbQAATEej?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNGgY-LaQAAkqqH?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNFoiYgbgAA0dJL?format=jpg&name=small',
    'https://pbs.twimg.com/media/HND6DXIbsAAFkWI?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNMSp-nXcAA7pnq?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLkpt8asAADGis?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNMVczXbkAAgHs0?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLxiMhaAAAYMtQ?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNOlhxMbsAEoE5U?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNHS3_fa8AARlmJ?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLqrCCbQAAkZHp?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNMSyW5boAAOcGl?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNKD0iTWMAAnrYu?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNMo41KaUAAU-YJ?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLxmXMbQAAzPNa?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNHhmXkbMAAMi9H?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNM4PHVaMAAat-q?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLvuRCboAAPv1c?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNOG_DEaAAAqND7?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLsqH3aQAEsTzh?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLp_11bUAAMaQC?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNMD8KDaAAAhC-E?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNPZk1IacAAoF5s?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNOYchlaMAAcSgO?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNH4dX0awAAw6kB?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNOnsrAaQAAesHc?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNNEU1TXUAAbWwp?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNJ8ipdbwAANjDJ?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNEoOm2aYAAUo8G?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLlwP7bwAA1lj0?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNBCYmbbsAAV799?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNMmiAZXEAA7ueD?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNPBDeyakAAuoEt?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNNdNN4aUAA68ga?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNK9VdcbAAA3k0k?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLkrlXaMAEMF9E?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNNXCDVbcAAQFCO?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNNge4RXkAAIj6w?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNM1EUCakAIkOuB?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNMWW7qaoAAFPil?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLn1AxbYAAzhWO?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNBCWj3agAILL_d?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNOP6gLbcAAoblM?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLri0NbMAASDbf?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNOB4szbcAAitJt?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNOrLcbbIAA_rnz?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNL8KLCbYAArFXX?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNBCOZHbgAA6LKm?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNOnpEdaEAA9S3b?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNGGwQwbYAA0r32?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNMGBDPaEAAoGul?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNGkigmbsAA0hXu?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLuYK4bkAEg0wY?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNHS_sEawAAIrxK?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNGbscvaMAAs63r?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNLHAhubwAAhhbh?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNJT7hOakAA-T1d?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNL3CUTaMAESFso?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNJ5HQUaAAAa3-F?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNMzDYkaUAAcb4H?format=jpg&name=small',
    'https://pbs.twimg.com/media/HNGb6AjawAEuwGI?format=jpg&name=small',










































































]